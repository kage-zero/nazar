"""Fast3R inference runner.

Runs INSIDE the isolated GPU environment (torch + fast3r; see `docs/ENVIRONMENT_SETUP.md`),
never in the worker's own environment, which stays free of torch. The worker starts it as a
subprocess and reads JSON events from stdout (one per line); logs go to stderr.

    python fast3r_runner.py --frames DIR --weights DIR --out DIR [--max-views N]

Frames are the `*.jpg` files in DIR, in sorted order. `--max-views 0` (default) sizes chunks
from free VRAM. More frames than the chunk size are run
in overlapping chunks. Each chunk is aligned to the frames already placed with a similarity
transform (scale, rotation, translation) fitted on the overlapping views. An overlapping view
appears in both chunks at identical pixels, so its two pointmaps give dense
correspondences.

Events:
    {"event": "loaded", ...}
    {"event": "plan", "max_views": n, "free_mib": m}
    {"event": "retry", "max_views": n, ...}       (out of memory; smaller chunks)
    {"event": "chunk", "index": i, "chunks": n, "path": ".../partial-i.npz", ...}
    {"event": "done", "path": ".../result.npz", ...}
    {"event": "error", "kind": "oom" | "failed", "message": "..."}  (exit code 3 / 1)

Each npz holds, for the views placed so far, all in the frame of the first view (OpenCV camera
axes: +X right, +Y down, +Z forward):
    pts (V, h, w, 3) float32, conf (V, h, w) float32, rgb (V, h, w, 3) uint8,
    c2w (V, 4, 4) float64, focal (V,) float64 (pixels at the model input size),
    views (V,) int64 (indices into the sorted frame list), input_size (2,) = (W, H).
"""

import argparse
import json
import struct
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

PER_VIEW_MIB = 215
MARGIN_MIB = 1536
# fp32 Fast3R ViT-L/512 is ~2.5 GiB; building it on the GPU needs that plus headroom.
FP32_BUILD_MIB = 3300


def emit(**event: Any) -> None:
    print(json.dumps(event), flush=True)


def chunk_ranges(n: int, max_views: int, overlap: int) -> list[list[int]]:
    if n <= max_views:
        return [list(range(n))]
    step = max(1, max_views - overlap)
    chunks, start = [], 0
    while True:
        end = min(start + max_views, n)
        chunks.append(list(range(max(0, end - max_views), end)))
        if end == n:
            return chunks
        start += step


def skeleton_chunks(n: int, max_views: int, anchors: int) -> list[list[int]]:
    """A first pass over `max_views` frames spread evenly over the whole sequence (the skeleton),
    then passes of consecutive new frames, each with the `anchors` skeleton frames nearest to
    them. Every pass is aligned directly to the skeleton through its anchors, so alignment
    errors do not accumulate along the sequence as they do with chained overlapping chunks."""
    if n <= max_views:
        return [list(range(n))]
    anchors = max(1, min(anchors, max_views - 1))
    skeleton = sorted({round(i * (n - 1) / (max_views - 1)) for i in range(max_views)})
    rest = [v for v in range(n) if v not in set(skeleton)]
    step = max_views - anchors
    passes = [skeleton]
    for start in range(0, len(rest), step):
        group = rest[start : start + step]
        centre = (group[0] + group[-1]) / 2
        near = sorted(skeleton, key=lambda k: (abs(k - centre), k))[:anchors]
        passes.append(sorted(group + near))
    return passes


def umeyama(src: np.ndarray, dst: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    """Least-squares similarity with dst ≈ s * R @ src + t."""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    xs, xd = src - mu_s, dst - mu_d
    cov = xd.T @ xs / len(src)
    u, d, vt = np.linalg.svd(cov)
    sign = np.eye(3)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        sign[2, 2] = -1
    rot = u @ sign @ vt
    var = (xs**2).sum() / len(src)
    scale = float(np.trace(np.diag(d) @ sign) / var)
    return scale, rot, mu_d - scale * rot @ mu_s


def robust_sim3(
    src: np.ndarray, dst: np.ndarray, rng: np.random.Generator
) -> tuple[float, np.ndarray, np.ndarray, float]:
    if len(src) > 60_000:
        pick = rng.choice(len(src), 60_000, replace=False)
        src, dst = src[pick], dst[pick]
    keep = np.ones(len(src), dtype=bool)
    for _ in range(4):
        s, r, t = umeyama(src[keep], dst[keep])
        res = np.linalg.norm(dst - (s * src @ r.T + t), axis=1)
        keep = res <= 2.5 * np.median(res[keep]) + 1e-12
    scale_ref = np.median(np.linalg.norm(dst - dst.mean(0), axis=1)) or 1.0
    return s, r, t, float(np.median(res[keep]) / scale_ref)


def peak_host_commit_mib() -> int | None:
    """Peak committed host memory of this process (Windows), or peak RSS elsewhere."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        get_info = kernel32.K32GetProcessMemoryInfo
        get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        get_info.restype = wintypes.BOOL
        if not get_info(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return None
        return round(counters.PeakPagefileUsage / 2**20)
    import resource

    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)


SAFETENSORS_DTYPES = {"F32": "float32", "F16": "float16", "BF16": "bfloat16", "I64": "int64"}


def read_safetensors_index(path: Path) -> dict[str, dict[str, Any]]:
    with path.open("rb") as f:
        (size,) = struct.unpack("<Q", f.read(8))
        header: dict[str, Any] = json.loads(f.read(size))
    header.pop("__metadata__", None)
    base = 8 + size
    for entry in header.values():
        entry["start"] = base + entry["data_offsets"][0]
        entry["end"] = base + entry["data_offsets"][1]
    return header


def iter_safetensors(path: Path, index: dict[str, dict[str, Any]]) -> Any:
    """Yield (name, CPU tensor) one at a time with plain reads. safetensors' own loader maps the
    file copy-on-write, which Windows charges against the commit limit in full (2.5 GiB)."""
    import torch

    with path.open("rb") as f:
        for name, entry in sorted(index.items(), key=lambda kv: kv[1]["start"]):
            dtype = SAFETENSORS_DTYPES.get(entry["dtype"])
            if dtype is None:
                raise RuntimeError(f"Unsupported checkpoint dtype {entry['dtype']} for {name}.")
            f.seek(entry["start"])
            data = bytearray(f.read(entry["end"] - entry["start"]))
            kind = getattr(torch, dtype)
            tensor = torch.frombuffer(data, dtype=kind) if data else torch.empty(0, dtype=kind)
            yield name, tensor.reshape(entry["shape"])


def load_model(cls: Any, weights: Path, dev: Any, dtype: Any) -> tuple[Any, Any]:
    """Fast3R.from_pretrained, but streaming the checkpoint one tensor at a time.

    from_pretrained materialises the whole fp32 state dict (2.5 GiB) in host memory next to an
    fp32 model built on the CPU. On a 16 GB laptop already running the web stack that hit the
    Windows commit limit ("paging file is too small", or an access violation inside the load).
    Here the model is built in fp32 on the GPU when it fits (upstream computes a
    non-checkpointed embedding buffer at init in fp32, so building in bf16 directly would not be
    equivalent), each tensor is read from the file and copied straight into its parameter, and
    the model is then cast. Host memory stays at about one tensor.
    """
    import torch

    config = json.loads((weights / "config.json").read_text(encoding="utf-8"))
    free_mib = torch.cuda.mem_get_info()[0] / 2**20
    build_on = dev if free_mib >= FP32_BUILD_MIB else torch.device("cpu")
    with build_on:
        model = cls(**config)
    targets = model.state_dict(keep_vars=True)
    stored = read_safetensors_index(weights / "model.safetensors")
    params = dict(model.named_parameters())
    missing = {k for k in params if k not in stored}
    unexpected = {k for k in stored if k not in targets}
    if missing or unexpected:
        raise RuntimeError(
            f"Checkpoint does not match the model: {len(missing)} missing, "
            f"{len(unexpected)} unexpected keys (e.g. {sorted(missing | unexpected)[:3]})."
        )
    with torch.no_grad():
        for key, tensor in iter_safetensors(weights / "model.safetensors", stored):
            targets[key].copy_(tensor)
    model = model.to(dtype).to(dev).eval()
    torch.cuda.empty_cache()
    return model, build_on


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=Path, required=True)
    ap.add_argument("--weights", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-views", type=int, default=0, help="0 = size from free VRAM.")
    ap.add_argument("--strategy", choices=["sequential", "skeleton"], default="sequential")
    ap.add_argument("--overlap", type=int, default=4, help="Shared views (sequential).")
    ap.add_argument("--anchors", type=int, default=3, help="Skeleton views per pass.")
    ap.add_argument("--stride", type=int, default=2, help="Keep every Nth pixel per axis.")
    ap.add_argument("--dtype", choices=["bf16", "fp16", "fp32"], default="bf16")
    args = ap.parse_args()

    import torch
    from fast3r.dust3r.inference_multiview import inference
    from fast3r.dust3r.utils.image import load_images
    from fast3r.models.fast3r import Fast3R
    from fast3r.models.multiview_dust3r_module import MultiViewDUSt3RLitModule

    files = sorted(str(p) for p in args.frames.glob("*.jpg"))
    if len(files) < 2:
        emit(event="error", kind="failed", message="Fast3R needs at least 2 frames.")
        return 1
    if not torch.cuda.is_available():
        emit(event="error", kind="failed", message="CUDA is not available to PyTorch.")
        return 1
    dtype = {"bf16": torch.bfloat16, "fp16": torch.float16, "fp32": torch.float32}[args.dtype]
    dev = torch.device("cuda")
    args.out.mkdir(parents=True, exist_ok=True)
    timings: dict[str, float] = {}

    t0 = time.monotonic()
    model, build_on = load_model(Fast3R, Path(args.weights), dev, dtype)
    # PyTorch wheels for Windows ship without the FlashAttention kernel the checkpoint asks for;
    # memory-efficient SDPA is the upstream-documented alternative (README: pytorch_auto).
    for module in model.modules():
        if getattr(module, "attn_implementation", None) == "flash_attention":
            module.attn_implementation = (
                "pytorch_auto" if type(module).__name__ == "Attention" else "pytorch_naive"
            )
    MultiViewDUSt3RLitModule.load_for_inference(model).eval()
    timings["load_s"] = round(time.monotonic() - t0, 3)
    emit(
        event="loaded",
        seconds=timings["load_s"],
        device=torch.cuda.get_device_name(0),
        built_on=build_on.type,
        weights_mib=round(torch.cuda.memory_allocated() / 2**20),
        frames=len(files),
    )

    def process(max_views: int) -> tuple[Path, int, list[dict[str, float]], float]:
        if args.strategy == "skeleton":
            chunks = skeleton_chunks(len(files), max_views, args.anchors)
        else:
            chunks = chunk_ranges(len(files), max_views, args.overlap)
        rng = np.random.default_rng(0)
        placed: dict[int, dict[str, np.ndarray]] = {}
        alignment: list[dict[str, float]] = []
        infer_s = 0.0
        size: tuple[int, int] = (0, 0)
        st = args.stride
        for ci, views in enumerate(chunks):
            t1 = time.monotonic()
            images = load_images([files[v] for v in views], size=512, verbose=False)
            with torch.no_grad():
                out = inference(images, model, dev, dtype=dtype, verbose=False)
            poses, focals = MultiViewDUSt3RLitModule.estimate_camera_poses(
                out["preds"],
                niter_PnP=100,
                focal_length_estimation_method="first_view_from_global_head",
            )
            torch.cuda.synchronize()
            infer_s += time.monotonic() - t1
            local = {}
            for j, v in enumerate(views):
                p = out["preds"][j]
                img = images[j]["img"][0].numpy()
                size = (img.shape[2], img.shape[1])
                local[v] = {
                    "pts": p["pts3d_in_other_view"][0].float().cpu().numpy()[::st, ::st],
                    "conf": p["conf"][0].float().cpu().numpy()[::st, ::st],
                    "rgb": ((img.transpose(1, 2, 0)[::st, ::st] + 1) * 127.5)
                    .clip(0, 255)
                    .astype(np.uint8),
                    "c2w": np.asarray(poses[0][j], dtype=np.float64),
                    "focal": np.float64(np.asarray(focals[0][j]).ravel()[0]),
                }
            del out
            torch.cuda.empty_cache()

            shared = [v for v in views if v in placed]
            if shared:
                src, dst = [], []
                for v in shared:
                    a, b = local[v], placed[v]
                    ok = (a["conf"] >= np.median(a["conf"])) & (b["conf"] >= np.median(b["conf"]))
                    src.append(a["pts"][ok])
                    dst.append(b["pts"][ok])
                s, r, t, rel = robust_sim3(np.concatenate(src), np.concatenate(dst), rng)
                alignment.append(
                    {"chunk": ci, "shared_views": len(shared), "scale": s, "residual_rel": rel}
                )
                for v in views:
                    if v in placed:
                        continue
                    item = local[v]
                    item["pts"] = (
                        (s * item["pts"].reshape(-1, 3) @ r.T + t)
                        .reshape(item["pts"].shape)
                        .astype(np.float32)
                    )
                    c2w = item["c2w"].copy()
                    c2w[:3, :3] = r @ c2w[:3, :3]
                    c2w[:3, 3] = s * r @ c2w[:3, 3] + t
                    item["c2w"] = c2w
                    placed[v] = item
            else:
                placed.update(local)

            order = sorted(placed)
            path = args.out / ("result.npz" if ci == len(chunks) - 1 else f"partial-{ci}.npz")
            np.savez(
                path,
                pts=np.stack([placed[v]["pts"] for v in order]),
                conf=np.stack([placed[v]["conf"] for v in order]),
                rgb=np.stack([placed[v]["rgb"] for v in order]),
                c2w=np.stack([placed[v]["c2w"] for v in order]),
                focal=np.array([placed[v]["focal"] for v in order]),
                views=np.array(order, dtype=np.int64),
                input_size=np.array(size),
            )
            peak = round(torch.cuda.max_memory_allocated() / 2**20)
            if ci < len(chunks) - 1:
                emit(
                    event="chunk",
                    index=ci,
                    chunks=len(chunks),
                    views=len(order),
                    path=str(path),
                    peak_vram_mib=peak,
                )
        return path, len(chunks), alignment, infer_s

    if args.max_views > 0:
        max_views = args.max_views
    else:
        # Measured on Fast3R ViT-L/512 in bf16: ~211 MiB per 512x288 view on top of the
        # weights. The margin covers the CUDA context, allocator fragmentation and the desktop.
        free_mib = torch.cuda.mem_get_info()[0] / 2**20
        max_views = int(max(2, min(48, (free_mib - MARGIN_MIB) // PER_VIEW_MIB)))
    emit(event="plan", max_views=max_views, free_mib=round(torch.cuda.mem_get_info()[0] / 2**20))
    while True:
        try:
            path, n_chunks, alignment, infer_s = process(max_views)
            break
        except torch.cuda.OutOfMemoryError as exc:
            # The caching allocator ran out: the context is still healthy, retry in-process.
            if max_views // 2 < 2:
                emit(event="error", kind="oom", message=str(exc).splitlines()[0][:300])
                return 3
            del exc
            torch.cuda.empty_cache()
            max_views //= 2
            emit(event="retry", max_views=max_views, reason="out of GPU memory")
        except RuntimeError as exc:
            if "CUDA error" not in str(exc):
                raise
            # A driver-level CUDA error (seen under VRAM pressure on 6 GB laptop GPUs) leaves
            # this process's context unusable: report it as OOM so the worker restarts the
            # runner with fewer views per pass.
            first = str(exc).splitlines()[0][:300]
            emit(event="error", kind="oom", message=first, max_views=max_views)
            return 3
    timings["inference_s"] = round(infer_s, 3)
    emit(
        event="done",
        path=str(path),
        chunks=n_chunks,
        max_views=max_views,
        alignment=alignment,
        peak_vram_mib=round(torch.cuda.max_memory_allocated() / 2**20),
        peak_host_commit_mib=peak_host_commit_mib(),
        timings=timings,
        torch=torch.__version__,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        emit(event="error", kind="failed", message=f"{type(exc).__name__}: {exc}"[:500])
        raise
