"""Export the domain validator's feature backbone to ONNX.

Source: torchvision ResNet-18, weights IMAGENET1K_V1, downloaded by torchvision
from download.pytorch.org/models/resnet18-f37072fd.pth (torchvision verifies the
hash prefix in the file name). The final classification layer is removed, leaving
the 512-d pooled features. Exported with ONNX opset 17.

Used by ml/grading/scripts/train_domain_validator.py (training) and by the
ml-service Dockerfile (build). With --verify, the exported backbone must reproduce
the reference output recorded in models/domain_validator/classifier.json (see
backbone_check.py), so a build can never pair the trained classifier with a
different backbone. Byte hashes are not compared: they vary across CPUs.

Licences: torchvision code is BSD-3-Clause. The pretrained weights were trained on
ImageNet; see https://pytorch.org/vision/stable/models.html for the terms that
apply to them.

Usage:
    python scripts/export_domain_backbone.py OUTPUT.onnx [--verify CLASSIFIER.json]
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
import torchvision

from backbone_check import verify_and_record


def export(output: Path) -> str:
    torch.manual_seed(0)
    model = torchvision.models.resnet18(weights=torchvision.models.ResNet18_Weights.IMAGENET1K_V1)
    model.fc = torch.nn.Identity()
    model.eval()
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        model, torch.zeros(1, 3, 224, 224), str(output),
        input_names=["input"], output_names=["features"],
        dynamic_axes={"input": {0: "batch"}, "features": {0: "batch"}},
        opset_version=17, dynamo=False,
    )

    # Numerical parity between torch and onnxruntime on a fixed input.
    import onnxruntime as ort
    probe = np.random.default_rng(42).standard_normal((2, 3, 224, 224)).astype(np.float32)
    with torch.no_grad():
        expected = model(torch.from_numpy(probe)).numpy()
    got = ort.InferenceSession(str(output), providers=["CPUExecutionProvider"]).run(None, {"input": probe})[0]
    if np.abs(expected - got).max() >= 1e-3:
        raise SystemExit("ONNX export does not match torch")
    return hashlib.sha256(output.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--verify", type=Path, help="classifier.json whose reference output the backbone must reproduce")
    args = parser.parse_args()

    digest = export(args.output)
    print(f"{args.output}: sha256 {digest} (torch {torch.__version__}, torchvision {torchvision.__version__})")
    if args.verify:
        backbone = json.loads(args.verify.read_text(encoding="utf-8"))["backbone"]
        max_diff = verify_and_record(args.output, backbone["reference"])
        same_bytes = "identical to" if digest == backbone["sha256"] else "different bytes from"
        print(f"Matches the trained classifier's reference output (max abs difference {max_diff:.2e}); "
              f"{same_bytes} the training export.")


if __name__ == "__main__":
    main()
