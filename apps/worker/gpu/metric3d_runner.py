"""Metric3D-v2 depth and surface normals per keyframe (BSD-2-Clause).

Runs INSIDE the main GPU environment, with the Metric3D source checkout on `--src`. Follows
the upstream torch.hub recipe (`hubconf.py`): keep-ratio resize into 616x1064, mean padding,
inference in the canonical camera (focal 1000), un-pad, resize back, then scale depth by
focal/1000 so it is metric *for the given intrinsics*. NAZAR's intrinsics are Fast3R's
estimate, so the worker labels anything derived from this depth as estimated.

    python metric3d_runner.py --frames DIR --intrinsics intr.json --src DIR --weights DIR
        --out DIR [--models vit_large,vit_small] [--budget-mib 5632]

intr.json: {"0000.jpg": {"fx": .., "cx": .., "cy": ..}, ...}
Writes NNNN.npz per frame: depth (H,W) f16 metres, normals (H,W,3) f16 in OpenCV camera axes
(+X right, +Y down, +Z forward, unit, facing the camera), normal_conf (H,W) f16; plus a
depth preview PNG. Models are tried largest first; the first that fits the budget is used.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from _common import Timer, budget, emit, is_oom, log, peak, run_main

CONFIGS = {
    "vit_small": ("vit.raft5.small.py", "metric_depth_vit_small_800k.pth"),
    "vit_large": ("vit.raft5.large.py", "metric_depth_vit_large_800k.pth"),
    "vit_giant2": ("vit.raft5.giant2.py", "metric_depth_vit_giant2_800k.pth"),
}
INPUT = (616, 1064)
MEAN = np.array([123.675, 116.28, 103.53], np.float32)
STD = np.array([58.395, 57.12, 57.375], np.float32)


def load(src: Path, weights: Path, name: str) -> Any:
    import torch

    sys.path.insert(0, str(src))
    try:
        from mmcv.utils import Config  # type: ignore[import-not-found]
    except ImportError:
        from mmengine import Config
    from mono.model.monodepth_model import get_configured_monodepth_model

    cfg_name, ckpt = CONFIGS[name]
    cfg = Config.fromfile(str(src / "mono" / "configs" / "HourglassDecoder" / cfg_name))
    model = get_configured_monodepth_model(cfg)
    state = torch.load(weights / ckpt, map_location="cpu", weights_only=False)["model_state_dict"]
    missing, _unexpected = model.load_state_dict(state, strict=False)
    if len(missing) > 10:
        raise RuntimeError(f"{ckpt} does not match the {name} model ({len(missing)} missing keys).")
    del state
    return model.cuda().eval()


def infer(model: Any, bgr: np.ndarray, fx: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    import torch
    import torch.nn.functional as F

    rgb = bgr[:, :, ::-1]
    h0, w0 = rgb.shape[:2]
    s = min(INPUT[0] / h0, INPUT[1] / w0)
    img = cv2.resize(rgb, (int(w0 * s), int(h0 * s)), interpolation=cv2.INTER_LINEAR)
    h, w = img.shape[:2]
    ph, pw = INPUT[0] - h, INPUT[1] - w
    pad = [ph // 2, ph - ph // 2, pw // 2, pw - pw // 2]
    img = cv2.copyMakeBorder(
        img, pad[0], pad[1], pad[2], pad[3], cv2.BORDER_CONSTANT, value=MEAN.tolist()
    )
    x = torch.from_numpy(((img.astype(np.float32) - MEAN) / STD).transpose(2, 0, 1))[None].cuda()
    with torch.no_grad():
        depth, _, out = model.inference({"input": x})
    depth = depth[0, 0, pad[0] : INPUT[0] - pad[1], pad[2] : INPUT[1] - pad[3]]
    depth = F.interpolate(depth[None, None], (h0, w0), mode="bilinear")[0, 0]
    depth = (depth * (fx * s) / 1000.0).clamp(0, 300)
    nrm = out["prediction_normal"][0, :, pad[0] : INPUT[0] - pad[1], pad[2] : INPUT[1] - pad[3]]
    nrm = F.interpolate(nrm[None], (h0, w0), mode="bilinear")[0]
    normals = F.normalize(nrm[:3], dim=0).permute(1, 2, 0)
    return depth.float().cpu().numpy(), normals.float().cpu().numpy(), nrm[3].float().cpu().numpy()


def facing_share(normals: np.ndarray, fx: float, cx: float, cy: float) -> float:
    """Share of pixels whose normal faces the camera, in OpenCV axes."""
    h, w = normals.shape[:2]
    u, v = np.meshgrid(np.arange(w), np.arange(h))
    rays = np.stack([(u - cx) / fx, (v - cy) / fx, np.ones_like(u, dtype=np.float64)], -1)
    return float(((normals * rays).sum(-1) < 0).mean())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=Path, required=True)
    ap.add_argument("--intrinsics", type=Path, required=True)
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--weights", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--models", default="vit_large,vit_small")
    ap.add_argument("--budget-mib", type=int, default=0)
    args = ap.parse_args()

    import torch

    timer = Timer()
    budget(args.budget_mib)
    intr = json.loads(args.intrinsics.read_text(encoding="utf-8"))
    files = sorted(args.frames.glob("*.jpg"))
    args.out.mkdir(parents=True, exist_ok=True)
    tried: list[dict[str, str]] = []
    for name in [m for m in args.models.split(",") if m]:
        if not (args.weights / CONFIGS[name][1]).is_file():
            tried.append({"model": name, "result": "weights not installed"})
            continue
        model = None
        try:
            model = load(args.src, args.weights, name)
            emit(event="loaded", model=name)
            convention = None
            facing = []
            for i, f in enumerate(files):
                k = intr[f.name]
                depth, normals, conf = infer(model, cv2.imread(str(f)), k["fx"])
                share = facing_share(normals, k["fx"], k["cx"], k["cy"])
                if convention is None:
                    # Decide once which axis convention the normals use (upstream does not
                    # document it): OpenCV, or OpenGL (+Y up, +Z backward).
                    gl = normals * np.array([1, -1, -1])
                    convention = (
                        "opencv"
                        if share >= facing_share(gl, k["fx"], k["cx"], k["cy"])
                        else "opengl"
                    )
                if convention == "opengl":
                    normals = normals * np.array([1, -1, -1], np.float32)
                    share = facing_share(normals, k["fx"], k["cx"], k["cy"])
                facing.append(share)
                np.savez(
                    args.out / f.name.replace(".jpg", ".npz"),
                    depth=depth.astype(np.float16),
                    normals=normals.astype(np.float16),
                    normal_conf=conf.astype(np.float16),
                )
                vis = cv2.applyColorMap(
                    cv2.normalize(
                        1 / np.maximum(depth, 1e-3), None, 0, 255, cv2.NORM_MINMAX
                    ).astype(np.uint8),
                    cv2.COLORMAP_TURBO,
                )
                nvis = ((normals + 1) * 127.5).clip(0, 255).astype(np.uint8)[:, :, ::-1]
                cv2.imwrite(
                    str(args.out / f.name),
                    np.concatenate([vis, nvis], 1),
                    [cv2.IMWRITE_JPEG_QUALITY, 85],
                )
                emit(event="progress", step="infer", done=i + 1, total=len(files))
            emit(
                event="done",
                model=name,
                tried=tried,
                frames=len(files),
                normal_convention=convention,
                normals_facing_camera=round(float(np.mean(facing)), 4),
                timings={"total_s": timer.s()},
                **peak(),
            )
            log(f"metric3d: {name}, {len(files)} frames")
            return 0
        except Exception as exc:
            if not is_oom(exc):
                raise
            tried.append({"model": name, "result": "out of GPU memory within the budget"})
            emit(event="retry", model=name, reason="out of GPU memory within the budget")
            del model
            torch.cuda.empty_cache()
    emit(event="error", kind="oom", message=f"No Metric3D variant fits the GPU budget: {tried}")
    return 3


if __name__ == "__main__":
    run_main(main)
