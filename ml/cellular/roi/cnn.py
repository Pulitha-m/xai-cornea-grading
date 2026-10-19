"""
Phase 6 — EfficientNet-B0 tile classifier (analysable vs poor).

Input: a (3, 162, 162) uint8 tile (raw / flat / lit planes, roi/tiles.py), resized
to input_px and ImageNet-normalised per channel. Augmentation: 90-degree rotations,
flips, brightness / contrast of the raw plane, mild noise. Fixed epochs, no early
stopping, so a held-out fold never influences training.
"""

from __future__ import annotations

import os

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)


def build(hp: dict) -> torch.nn.Module:
    import torchvision
    weights = "IMAGENET1K_V1" if hp["pretrained"] else None
    model = getattr(torchvision.models, hp["arch"])(weights=weights)
    model.classifier[-1] = torch.nn.Linear(model.classifier[-1].in_features, 1)
    return model


def to_input(tiles: torch.Tensor, input_px: int) -> torch.Tensor:
    """uint8 (N, 3, s, s) -> normalised float (N, 3, input_px, input_px)."""
    x = tiles.float() / 255
    x = F.interpolate(x, size=(input_px, input_px), mode="bilinear", align_corners=False)
    return (x - MEAN.to(x.device)) / STD.to(x.device)


def augment(tile: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    t = np.rot90(tile, rng.integers(4), axes=(1, 2))
    if rng.random() < 0.5:
        t = t[:, :, ::-1]
    t = t.astype(np.float32)
    t[0] = t[0] * rng.uniform(0.75, 1.25) + rng.uniform(-20, 20)          # brightness / contrast (raw)
    t[:2] += rng.normal(0, rng.uniform(0, 4), t[:2].shape)                 # mild noise
    return np.clip(t, 0, 255).astype(np.uint8)


class TileSet(Dataset):
    def __init__(self, tiles: np.ndarray, y: np.ndarray):
        self.tiles, self.y = tiles, y.astype(np.float32)

    def __len__(self) -> int:
        return len(self.tiles)

    def __getitem__(self, i):
        rng = np.random.default_rng(int(torch.randint(0, 2**31 - 1, (1,))))   # follows torch seeding
        return torch.from_numpy(augment(self.tiles[i], rng).copy()), torch.tensor(self.y[i])


def train(tiles: np.ndarray, y: np.ndarray, hp: dict, device: torch.device, seed: int,
          epochs: int | None = None) -> torch.nn.Module:
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = build(hp).to(device)
    loader = DataLoader(TileSet(tiles, y), batch_size=hp["batch_size"], shuffle=True, drop_last=True,
                        num_workers=0 if os.name == "nt" else 2,          # Windows: no worker processes
                        pin_memory=device.type == "cuda")
    epochs = epochs or hp["epochs"]
    opt = torch.optim.AdamW(model.parameters(), lr=hp["lr"], weight_decay=hp["weight_decay"])
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=hp["lr"], total_steps=epochs * len(loader))
    use_amp = device.type == "cuda"
    scaler = torch.amp.GradScaler(device.type, enabled=use_amp)
    model.train()
    for ep in range(epochs):
        total = 0.0
        for xb, yb in loader:
            xb, yb = to_input(xb.to(device), hp["input_px"]), yb.to(device)
            with torch.autocast(device.type, enabled=use_amp):
                loss = F.binary_cross_entropy_with_logits(model(xb).squeeze(1).float(), yb)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            total += loss.item()
        if ep == 0 or (ep + 1) % 5 == 0 or ep + 1 == epochs:
            print(f"    epoch {ep + 1}/{epochs}  loss {total / len(loader):.4f}", flush=True)
    return model


@torch.no_grad()
def predict(model: torch.nn.Module, tiles: np.ndarray, hp: dict, device: torch.device,
            batch: int = 128) -> np.ndarray:
    """P(analysable) per tile."""
    model.eval()
    out = []
    for i in range(0, len(tiles), batch):
        xb = to_input(torch.from_numpy(np.ascontiguousarray(tiles[i:i + batch])).to(device), hp["input_px"])
        with torch.autocast(device.type, enabled=device.type == "cuda"):
            out.append(torch.sigmoid(model(xb).float()).squeeze(1).cpu().numpy())
    return np.concatenate(out) if out else np.zeros(0, np.float32)
