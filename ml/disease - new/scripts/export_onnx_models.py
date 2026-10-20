"""Export the v2 disease and severity models to ONNX for ml-service (CPU, no torch at runtime).

The model classes are copied exactly from notebooks/10_Inference_Final_Models_v2.ipynb
(Step 6), so the trained state_dicts load with strict=True:

- Fusion (disease): DenseNet121 features + MLP on the 6 scaled numbers -> 5 disease logits.
- FusionMultiTask (severity): same structure -> 5 disease logits + 3 severity logits.

The disease graph also returns, for each of the 5 diseases, the Grad-CAM map of the
DenseNet `features` layer (the notebook's cam_layer) and the L2-normalised backbone
embedding used by the unusual-image check. Grad-CAM needs d(logit)/d(features); after
`features` the network is relu -> global average pool -> [concat tab MLP] -> Linear ->
ReLU -> Linear, so that gradient has a closed form and is computed inside the graph.
The export checks it against torch autograd Grad-CAM (the notebook's gradcam()).

Checks before the files are accepted (the script fails otherwise):
- ONNX outputs equal the torch outputs on real-looking inputs (max abs diff < 1e-4);
- the closed-form Grad-CAM equals autograd Grad-CAM (max abs diff < 1e-4 after
  min-max normalisation, as the notebook displays it).

Records file names, SHA-256 and the parity results under "models" in
corneal_config.json (written by export_corneal_config.py, run that first).

Usage (needs torch, torchvision, onnx, onnxruntime):
    python "ml/disease-new/scripts/export_onnx_models.py" --weights-dir ml-service/models/disease_v2
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision
from torchvision import models

REPO_DIR = Path(__file__).resolve().parents[3]
DEFAULT_DIR = REPO_DIR / "ml-service" / "models" / "disease_v2"

N_FEATURES = 6
N_DISEASES = 5
IMG_H, IMG_W = 288, 384
OPSET = 17


# --- Model classes: identical to notebook 10, Step 6 -------------------------------
def densenet():
    m = models.densenet121(weights=None); dim = m.classifier.in_features; m.classifier = nn.Identity()
    return m, dim


class Fusion(nn.Module):                     # disease model
    def __init__(self):
        super().__init__()
        self.backbone, dim = densenet(); self.cam_layer = self.backbone.features
        self.tab_mlp = nn.Sequential(nn.Linear(N_FEATURES, 32), nn.ReLU(), nn.Dropout(0.2), nn.Linear(32, 32), nn.ReLU())
        self.head = nn.Sequential(nn.Dropout(0.3), nn.Linear(dim + 32, 128), nn.ReLU(), nn.Dropout(0.3), nn.Linear(128, N_DISEASES))

    def forward(self, x, tab):
        return self.head(torch.cat([self.backbone(x), self.tab_mlp(tab)], 1))


class FusionMultiTask(nn.Module):            # severity model
    def __init__(self, n_severity):
        super().__init__()
        self.backbone, dim = densenet(); self.cam_layer = self.backbone.features
        self.tab_mlp = nn.Sequential(nn.Linear(N_FEATURES, 32), nn.ReLU(), nn.Dropout(0.2), nn.Linear(32, 32), nn.ReLU())
        self.shared = nn.Sequential(nn.Dropout(0.3), nn.Linear(dim + 32, 128), nn.ReLU(), nn.Dropout(0.3))
        self.disease_head = nn.Linear(128, N_DISEASES)
        self.severity_head = nn.Linear(128, n_severity)

    def forward(self, x, tab):
        z = self.shared(torch.cat([self.backbone(x), self.tab_mlp(tab)], 1))
        return self.disease_head(z), self.severity_head(z)


# --- Export wrappers ---------------------------------------------------------------
class DiseaseExport(nn.Module):
    """logits (B,5), cams (B,5,h,w) before resizing/normalising, embedding (B,1024) L2-normalised."""

    def __init__(self, model: Fusion):
        super().__init__()
        self.m = model

    def forward(self, image, tab):
        acts = self.m.backbone.features(image)                       # cam_layer output (B,C,h,w)
        pooled = F.adaptive_avg_pool2d(F.relu(acts), (1, 1)).flatten(1)
        z = torch.cat([pooled, self.m.tab_mlp(tab)], 1)
        lin1, lin2 = self.m.head[1], self.m.head[4]
        hidden = lin1(z)
        logits = lin2(F.relu(hidden))

        # d logit_j / d pooled  =  W1[:, :C]^T (W2[j] * relu'(hidden))
        gate = (hidden > 0).to(hidden.dtype)                          # (B,128)
        grad_z = (lin2.weight.unsqueeze(0) * gate.unsqueeze(1)) @ lin1.weight   # (B,5,C+32)
        grad_pooled = grad_z[:, :, : acts.shape[1]]                   # (B,5,C)
        # d pooled_c / d acts_chw = relu'(acts_chw) / (h*w); Grad-CAM weight = spatial mean of the gradient
        hw = acts.shape[2] * acts.shape[3]
        active = (acts > 0).to(acts.dtype).mean(dim=(2, 3))           # (B,C)
        weights = grad_pooled * active.unsqueeze(1) / hw              # (B,5,C)
        # torchvision's DenseNet.forward applies relu(features, inplace=True), so the activations the
        # notebook's forward hook keeps are relu(acts) by the time Grad-CAM reads them.
        cams = F.relu(torch.einsum("bjc,bchw->bjhw", weights, F.relu(acts)))
        embedding = F.normalize(pooled, dim=1)
        return logits, cams, embedding, pooled


class SeverityExport(nn.Module):
    def __init__(self, model: FusionMultiTask):
        super().__init__()
        self.m = model

    def forward(self, image, tab):
        pooled = self.m.backbone(image)
        z = self.m.shared(torch.cat([pooled, self.m.tab_mlp(tab)], 1))
        return self.m.disease_head(z), self.m.severity_head(z), pooled


# --- Head weights for SHAP on the numbers (image features fixed) ----------------------
def head_arrays(dis: Fusion, sev: FusionMultiTask) -> dict:
    """Layers after the backbone, so ml-service can re-run them in numpy for many number inputs."""
    def lin(prefix, layer):
        return {f"{prefix}_w": layer.weight.detach().numpy(), f"{prefix}_b": layer.bias.detach().numpy()}
    return {
        **lin("dis_tab1", dis.tab_mlp[0]), **lin("dis_tab2", dis.tab_mlp[3]),
        **lin("dis_head1", dis.head[1]), **lin("dis_head2", dis.head[4]),
        **lin("sev_tab1", sev.tab_mlp[0]), **lin("sev_tab2", sev.tab_mlp[3]),
        **lin("sev_shared", sev.shared[1]), **lin("sev_disease", sev.disease_head), **lin("sev_severity", sev.severity_head),
    }


def numpy_heads(h: dict, pooled_dis, pooled_sev, tab):
    """Same computation as ml-service pipelines/disease/explain.py (checked against torch here)."""
    relu = lambda a: np.maximum(a, 0)
    dense = lambda x, p: x @ h[f"{p}_w"].T + h[f"{p}_b"]
    t = relu(dense(relu(dense(tab, "dis_tab1")), "dis_tab2"))
    dis_logits = dense(relu(dense(np.concatenate([pooled_dis, t], 1), "dis_head1")), "dis_head2")
    t = relu(dense(relu(dense(tab, "sev_tab1")), "sev_tab2"))
    z = relu(dense(np.concatenate([pooled_sev, t], 1), "sev_shared"))
    return dis_logits, dense(z, "sev_severity")


# --- Reference implementations from the notebook -------------------------------------
def autograd_gradcam(model: Fusion, x, tab, j):
    """notebook 10 gradcam(), without the final resize (compared at feature-map size)."""
    acts, grads = {}, {}

    def hook(m, i, o):
        acts["a"] = o
        o.register_hook(lambda g: grads.__setitem__("g", g))

    h = model.cam_layer.register_forward_hook(hook)
    with torch.enable_grad():
        model.zero_grad(); model(x, tab)[0, j].backward()
    h.remove()
    w = grads["g"].mean(dim=(2, 3), keepdim=True)
    return torch.relu((w * acts["a"]).sum(1)).squeeze().detach().numpy()


def minmax(a):
    return (a - a.min()) / (a.max() - a.min() + 1e-8)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe_inputs():
    """Image-like inputs: smoothed noise normalised like a greyscale specular image, plus scaled numbers."""
    rng = np.random.default_rng(7)
    grey = rng.uniform(0.2, 0.8, size=(2, 1, IMG_H, IMG_W)).astype(np.float32)
    grey = F.avg_pool2d(torch.from_numpy(grey), 5, stride=1, padding=2)
    mean = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
    image = ((grey.repeat(1, 3, 1, 1) - mean) / std).float()
    tab = torch.from_numpy(rng.standard_normal((2, N_FEATURES)).astype(np.float32))
    return image, tab


def export(module, path: Path, output_names, dynamic_out):
    image, tab = probe_inputs()
    torch.onnx.export(
        module, (image, tab), str(path),
        input_names=["image", "tab"], output_names=output_names,
        dynamic_axes={"image": {0: "batch"}, "tab": {0: "batch"}, **{n: {0: "batch"} for n in dynamic_out}},
        opset_version=OPSET, dynamo=False,
    )


def run_onnx(path: Path, image, tab):
    import onnxruntime as ort
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    return session.run(None, {"image": image.numpy(), "tab": tab.numpy()})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights-dir", type=Path, default=DEFAULT_DIR,
                        help="Folder with Image_plus_numbers.pt, final_multitask.pt and corneal_config.json")
    parser.add_argument("--out-dir", type=Path, default=None, help="Defaults to --weights-dir")
    args = parser.parse_args()
    out_dir = args.out_dir or args.weights_dir
    config_path = out_dir / "corneal_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    n_severity = len(config["severity_heads"])
    torch.manual_seed(0)

    dis = Fusion()
    dis.load_state_dict(torch.load(args.weights_dir / "Image_plus_numbers.pt", map_location="cpu"), strict=True)
    dis.eval()
    sev = FusionMultiTask(n_severity)
    sev.load_state_dict(torch.load(args.weights_dir / "final_multitask.pt", map_location="cpu"), strict=True)
    sev.eval()

    image, tab = probe_inputs()

    # Disease model.
    dis_path = out_dir / "disease_fusion_densenet121.onnx"
    wrapper = DiseaseExport(dis).eval()
    export(wrapper, dis_path, ["logits", "cams", "embedding", "pooled"], ["logits", "cams", "embedding", "pooled"])
    with torch.no_grad():
        t_logits, t_cams, t_emb, _ = wrapper(image, tab)
        ref_logits = dis(image, tab)
        ref_emb = F.normalize(dis.backbone(image), dim=1)
    assert torch.allclose(t_logits, ref_logits, atol=1e-5), "wrapper logits differ from the notebook model"
    assert torch.allclose(t_emb, ref_emb, atol=1e-5), "wrapper embedding differs from the notebook embed()"
    cam_diff = max(float(np.abs(minmax(t_cams[0, j].numpy()) - minmax(autograd_gradcam(dis, image[:1], tab[:1], j))).max())
                   for j in range(N_DISEASES))
    assert cam_diff < 1e-4, f"closed-form Grad-CAM differs from autograd Grad-CAM ({cam_diff:.2e})"
    o_logits, o_cams, o_emb, o_pooled_dis = run_onnx(dis_path, image, tab)
    dis_diff = max(float(np.abs(o_logits - t_logits.numpy()).max()),
                   float(np.abs(o_emb - t_emb.numpy()).max()),
                   max(float(np.abs(minmax(o_cams[0, j]) - minmax(t_cams[0, j].numpy())).max()) for j in range(N_DISEASES)))
    assert dis_diff < 1e-4, f"ONNX disease model differs from torch ({dis_diff:.2e})"

    # Severity model.
    sev_path = out_dir / "severity_multitask_densenet121.onnx"
    export(SeverityExport(sev).eval(), sev_path, ["disease_logits", "severity_logits", "pooled"],
           ["disease_logits", "severity_logits", "pooled"])
    with torch.no_grad():
        s_dis, s_sev = sev(image, tab)
    o_dis, o_sev, o_pooled_sev = run_onnx(sev_path, image, tab)
    sev_diff = max(float(np.abs(o_dis - s_dis.numpy()).max()), float(np.abs(o_sev - s_sev.numpy()).max()))
    assert sev_diff < 1e-4, f"ONNX severity model differs from torch ({sev_diff:.2e})"

    # Head weights: numpy re-run from the ONNX pooled features must reproduce the torch outputs.
    heads_path = out_dir / "heads.npz"
    heads = head_arrays(dis, sev)
    np.savez(heads_path, **heads)
    n_dis, n_sev = numpy_heads(heads, o_pooled_dis, o_pooled_sev, tab.numpy())
    heads_diff = max(float(np.abs(n_dis - t_logits.numpy()).max()), float(np.abs(n_sev - s_sev.numpy()).max()))
    assert heads_diff < 1e-4, f"numpy heads differ from torch ({heads_diff:.2e})"

    config["models"] = {
        "exported_with": {"torch": torch.__version__, "torchvision": torchvision.__version__, "opset": OPSET},
        "disease": {
            "file": dis_path.name, "sha256": sha256(dis_path),
            "source_weights": "final_densenet121/Image_plus_numbers.pt",
            "source_sha256": sha256(args.weights_dir / "Image_plus_numbers.pt"),
            "inputs": {"image": [None, 3, IMG_H, IMG_W], "tab": [None, N_FEATURES]},
            "outputs": ["logits", "cams", "embedding", "pooled"],
            "max_abs_difference_vs_torch": dis_diff,
            "gradcam_max_abs_difference_vs_autograd": cam_diff,
        },
        "severity": {
            "file": sev_path.name, "sha256": sha256(sev_path),
            "source_weights": "severity_densenet121/final_multitask.pt",
            "source_sha256": sha256(args.weights_dir / "final_multitask.pt"),
            "inputs": {"image": [None, 3, IMG_H, IMG_W], "tab": [None, N_FEATURES]},
            "outputs": ["disease_logits", "severity_logits", "pooled"],
            "max_abs_difference_vs_torch": sev_diff,
        },
        "heads": {
            "file": heads_path.name, "sha256": sha256(heads_path),
            "description": "tab MLP and heads of both models, for exact SHAP on the numbers (image fixed)",
            "max_abs_difference_vs_torch": heads_diff,
        },
    }
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"disease : {dis_path.name} ({dis_path.stat().st_size / 1e6:.1f} MB) ONNX vs torch {dis_diff:.1e}, "
          f"Grad-CAM vs autograd {cam_diff:.1e}")
    print(f"severity: {sev_path.name} ({sev_path.stat().st_size / 1e6:.1f} MB) ONNX vs torch {sev_diff:.1e}")
    print(f"Recorded in {config_path}")


if __name__ == "__main__":
    main()
