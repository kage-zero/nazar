# 02 — Depth Priors (Metric3D-v2)

## 1. Overview & Purpose

In single-pass aerial footage, large uniform surfaces (asphalt roads, flat rooftops, water bodies, homogeneous fields) lack distinct feature points. Multi-view matching models like Fast3R or classical SfM leave these areas completely hollow.

**Metric3D-v2** solves this by providing:
1. **Zero-shot Metric Depth Maps**: Predicts physical metric depth (in meters) for every single pixel from monocular images.
2. **Surface Normal Fields**: Predicts per-pixel surface orientations ($\vec{n}_x, \vec{n}_y, \vec{n}_z$) with crisp edge preservation.

These priors directly feed into the `surface_processing` stage to guide Poisson meshing and fill in untextured voids.

---

## 2. Model Specs & License

* **Paper**: *Metric3D v2: A Versatile Monocular Geometric Foundation Model for Zero-shot Metric Depth and Surface Normal Estimation* (arXiv:2404.15506).
* **Official Repository**: [`YvanYin/Metric3D`](https://github.com/YvanYin/Metric3D)
* **Licence**: **BSD 2-Clause License** (Completely free for academic and commercial use).
* **Recommended Checkpoint**: `metric_depth_vit_large_800k.pth` (~1.2 GB) or `viplab/metric3d-vit-large` on Hugging Face.
* **Hardware**: PyTorch on CUDA (runs in ~150 ms per keyframe on an RTX 4050).

---

## 3. Architecture & Environment Isolation (ADR-0004)

In accordance with [ADR-0004](../decisions/ADR-0004-isolated-model-environments.md), Metric3D runs in an isolated runner environment or subprocess (`apps/worker/gpu/metric3d_runner.py`) so its PyTorch dependencies never conflict with the main worker orchestrator.

```
apps/api/
    │
    ▼ (Keyframe images)
apps/worker/
    │
    ▼ (IPC via subprocess)
apps/worker/gpu/metric3d_runner.py ──▶ [Metric3D-v2 Model]
    │                                          │
    ▼ (Artifacts: depth.npy, normals.png) ◀───┘
```

---

## 4. Runner Implementation (`metric3d_runner.py`)

```python
"""Metric3D-v2 standalone inference runner."""

import sys
import torch
import cv2
import numpy as np
from pathlib import Path

# Load model via torch.hub or HuggingFace checkpoint
def load_metric3d(checkpoint_path: Path, device: str = "cuda"):
    model = torch.hub.load("yvanyin/metric3d", "metric3d_vit_large", pretrained=False)
    state_dict = torch.load(checkpoint_path, map_location=device)
    model.load_state_dict(state_dict["model"])
    model.to(device).eval()
    return model

@torch.no_grad()
def predict_depth_and_normals(model, image_bgr: np.ndarray, intrinsics_fx_fy_cx_cy: tuple):
    """Predict metric depth (meters) and surface normals."""
    h, w = image_bgr.shape[:2]
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    
    # Preprocess image and canonical camera transform
    input_tensor = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
    input_tensor = input_tensor.unsqueeze(0).cuda()
    
    # Model forward pass
    pred_depth, confidence, pred_normals = model(input_tensor, intrinsics=intrinsics_fx_fy_cx_cy)
    
    depth_m = pred_depth.squeeze().cpu().numpy()
    normals = pred_normals.squeeze().permute(1, 2, 0).cpu().numpy()
    return depth_m, normals
```

---

## 5. Integrating with the NAZAR Pipeline

In [`apps/worker/src/nazar_worker/standard.py`](../../apps/worker/src/nazar_worker/standard.py):

Replace `StageName.DEPTH_PRIORS: Skip(...)`:

```python
class DepthPriors(_Stage):
    def run(self, ctx: StageContext) -> None:
        run = self.run_state
        ctx.progress("Inferring monocular metric depth & surface normals", 0, len(run.images), "keyframes")
        
        # 1. Run runner subprocess on each keyframe
        depth_maps = []
        normal_maps = []
        for i, img in enumerate(run.images):
            depth, normals = run_metric3d_inference(img)
            depth_maps.append(depth)
            normal_maps.append(normals)
            ctx.progress("Computed depth priors", i + 1, len(run.images), "keyframes")

        # 2. Package and publish depth artifact
        depth_archive = serialize_depth_maps(depth_maps)
        ctx.publish(
            _declare(
                run,
                "depth-maps",
                ArtifactKind.DEPTH_MAPS,
                "application/x-numpy",
                depth_archive,
                final=True,
            ),
            depth_archive,
        )
        
        # 3. Store in run state for the surface mesher
        run.depth_maps = depth_maps
        run.normal_maps = normal_maps
```

---

## 6. How Depth Priors Improve the Surface Mesh

When [`01-SURFACE-MESHING.md`](01-SURFACE-MESHING.md) runs:
1. Instead of estimating point cloud normals purely from noisy $k$-NN neighbor search, it samples true physical surface normals from Metric3D's `normal_maps`.
2. Roofs, walls, and roads become planar and crisp without bumpy Poisson noise.
3. Points unprojected from Metric3D depth maps populate the hollow, featureless ground.
