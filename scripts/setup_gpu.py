"""Set up (or check) the GPU model environments for NAZAR's full pipeline.

Usage (repo root):
    uv run python scripts/setup_gpu.py --check                  # read-only verification
    uv run python scripts/setup_gpu.py --profile local          # install for the 6 GB laptop
    uv run python scripts/setup_gpu.py --profile clg            # install for the college GPU

Installs under var/gpu/ (git-ignored), everything pinned:

    fast3r-src/ sam2-src/ metric3d-src/   model source checkouts at fixed commits
    main-env/    Python 3.11: torch 2.6.0+cu124, Fast3R, Open3D, Ultralytics YOLO, SAM 2,
                 Metric3D-v2 deps (apps/worker/gpu/requirements-main.txt)
    splat-env/   Python 3.10: torch 2.4.1+cu124 + gsplat 1.5.3 (prebuilt wheel exists only
                 for this combination) (apps/worker/gpu/requirements-splat.txt)
    weights/     checkpoints for the chosen profile (SHA-256 checked where pinned)

Before downloading anything it prints what is missing and the approximate size, and asks
for confirmation (or pass --yes). Licences: Fast3R FAIR Noncommercial (academic use
approved), SAM 2 Apache-2.0, Metric3D BSD-2-Clause, Ultralytics AGPL-3.0 (accepted for this
academic project), gsplat Apache-2.0. No token is needed.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GPU = REPO_ROOT / "var" / "gpu"
REQS = REPO_ROOT / "apps" / "worker" / "gpu"
HF = "https://huggingface.co"
MIB = 2**20


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    commit: str


@dataclass(frozen=True)
class Weight:
    path: str
    url: str
    size: int
    sha256: str | None
    profiles: tuple[str, ...]


SOURCES = (
    Source(
        "fast3r-src",
        "https://github.com/facebookresearch/fast3r.git",
        "33104d4b5b8df43795ecded236194958bbdac572",
    ),
    Source(
        "sam2-src",
        "https://github.com/facebookresearch/sam2.git",
        "2b90b9f5ceec907a1c18123530e92e794ad901a4",
    ),
    Source(
        "metric3d-src",
        "https://github.com/YvanYin/Metric3D.git",
        "eb5b6fac0dc155e4e52f576e304fbf11655ff339",
    ),
)
FAST3R = f"{HF}/jedyang97/Fast3R_ViT_Large_512/resolve/a2c770b768ceb3a53c36c4f7a3619db0413dc3a1"
SAM2 = "https://dl.fbaipublicfiles.com/segment_anything_2/092824"
M3D = f"{HF}/JUGGHM/Metric3D/resolve/main"
YOLO = "https://github.com/ultralytics/assets/releases/download/v8.3.0"
BOTH = ("local", "clg")
WEIGHTS = (
    Weight(
        "Fast3R_ViT_Large_512/config.json",
        f"{FAST3R}/config.json",
        941,
        "88edc53ba652ad835b86af27d980a46808d722b4d8f9d0d4360d05c789ada92b",
        BOTH,
    ),
    Weight(
        "Fast3R_ViT_Large_512/model.safetensors",
        f"{FAST3R}/model.safetensors",
        2590286416,
        "1357d42e74539ba03510ea1986c7464a7facf17157779e2b7ebd6284e79e0427",
        BOTH,
    ),
    Weight(
        "yolo/yolo11s.pt",
        f"{YOLO}/yolo11s.pt",
        19313732,
        "85a76fe86dd8afe384648546b56a7a78580c7cb7b404fc595f97969322d502d5",
        ("local",),
    ),
    Weight("yolo/yolo11x.pt", f"{YOLO}/yolo11x.pt", 114_000_000, None, ("clg",)),
    Weight(
        "sam2/sam2.1_hiera_small.pt",
        f"{SAM2}/sam2.1_hiera_small.pt",
        184416285,
        "6d1aa6f30de5c92224f8172114de081d104bbd23dd9dc5c58996f0cad5dc4d38",
        ("local",),
    ),
    Weight(
        "sam2/sam2.1_hiera_large.pt", f"{SAM2}/sam2.1_hiera_large.pt", 898_000_000, None, ("clg",)
    ),
    Weight(
        "metric3d/metric_depth_vit_small_800k.pth",
        f"{M3D}/metric_depth_vit_small_800k.pth",
        150120967,
        "b34b2a2be9148054991cef7e417930e1320602ba7bc503b0ee4e7888543728f6",
        ("local",),
    ),
    Weight(
        "metric3d/metric_depth_vit_large_800k.pth",
        f"{M3D}/metric_depth_vit_large_800k.pth",
        1647972663,
        "15328ffc42b528b95f188687418f6f03b3f123eb34ccdbd686c112abbea6d972",
        BOTH,
    ),
    Weight(
        "metric3d/metric_depth_vit_giant2_800k.pth",
        f"{M3D}/metric_depth_vit_giant2_800k.pth",
        5_510_000_000,
        None,
        ("clg",),
    ),
)
ENVS = {
    "main-env": ("3.11", REQS / "requirements-main.txt", 3_300 * MIB),
    "splat-env": ("3.10", REQS / "requirements-splat.txt", 2_600 * MIB),
}
PROBES = {
    "main-env": "import json, torch, open3d, fast3r, sam2, ultralytics, mmengine, timm; "
    "print(json.dumps({'torch': torch.__version__, 'cuda': torch.cuda.is_available()}))",
    "splat-env": "import json, torch, gsplat; "
    "print(json.dumps({'torch': torch.__version__, 'cuda': torch.cuda.is_available()}))",
}


def python_of(env: str) -> Path:
    return GPU / env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def run(cmd: list[str], env: dict[str, str] | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    # Fixed argv built in this file (git, uv, the GPU interpreters); no user input reaches it.
    subprocess.run(cmd, check=True, env=env)  # noqa: S603


def commit_of(path: Path) -> str | None:
    if not (path / ".git").exists():
        return None
    out = subprocess.run(  # noqa: S603 - fixed argv
        ["git", "-C", str(path), "rev-parse", "HEAD"],  # noqa: S607 - git from PATH
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.strip() or None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 24), b""):
            digest.update(block)
    return digest.hexdigest()


def probe(env: str) -> str | None:
    """None when the environment imports its stack with CUDA available; else the problem."""
    if not python_of(env).is_file():
        return f"{env} is not created"
    out = subprocess.run(  # noqa: S603 - the GPU interpreter with a fixed probe
        [str(python_of(env)), "-W", "ignore", "-c", PROBES[env]],
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [ln for ln in out.stdout.splitlines() if ln.startswith("{")]
    if out.returncode or not lines:
        tail = (out.stderr.strip().splitlines() or ["?"])[-1]
        return f"{env} cannot import its packages ({tail[:160]})"
    info = json.loads(lines[-1])
    print(f"  {env}: torch {info['torch']}, CUDA available: {info['cuda']}")
    return None if info["cuda"] else f"{env}: CUDA is not available to PyTorch"


def missing_weights(profile: str, verify: bool) -> list[Weight]:
    out = []
    for w in WEIGHTS:
        if profile not in w.profiles and profile != "all":
            continue
        path = GPU / "weights" / w.path
        if not path.is_file():
            out.append(w)
        elif verify and w.sha256 and sha256(path) != w.sha256:
            print(f"  {w.path}: checksum mismatch")
            out.append(w)
    return out


def check(profile: str, verify: bool) -> list[str]:
    problems = []
    for src in SOURCES:
        if commit_of(GPU / src.name) != src.commit:
            problems.append(f"{src.name}: expected commit {src.commit[:7]}")
    for env in ENVS:
        if (problem := probe(env)) is not None:
            problems.append(problem)
    problems += [f"weights missing: {w.path}" for w in missing_weights(profile, verify)]
    return problems


def download(w: Weight) -> None:
    dest = GPU / "weights" / w.path
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    print(f"  downloading {w.path} (~{w.size / MIB:,.0f} MiB)", flush=True)
    if shutil.which("curl"):
        run(["curl", "-fL", "--retry", "3", "-C", "-", "-o", str(part), w.url])
    else:
        urllib.request.urlretrieve(w.url, part)  # noqa: S310 - fixed https URLs above
    if w.sha256 and sha256(part) != w.sha256:
        raise SystemExit(f"{w.path}: downloaded file does not match the pinned SHA-256.")
    part.replace(dest)


def install(profile: str, yes: bool) -> None:
    if shutil.which("git") is None or shutil.which("uv") is None:
        raise SystemExit("git and uv must be on PATH.")
    GPU.mkdir(parents=True, exist_ok=True)
    todo_src = [s for s in SOURCES if commit_of(GPU / s.name) != s.commit]
    todo_env = [e for e in ENVS if probe(e) is not None]
    todo_w = missing_weights(profile, verify=False)
    total = sum(w.size for w in todo_w) + sum(ENVS[e][2] for e in todo_env)
    total += 350 * MIB * len(todo_src)
    if not (todo_src or todo_env or todo_w):
        return
    print("To download / install:")
    for s in todo_src:
        print(f"  source  {s.name} @ {s.commit[:7]}")
    for e in todo_env:
        print(f"  env     {e} (~{ENVS[e][2] / MIB:,.0f} MiB of packages, less if cached)")
    for w in todo_w:
        print(f"  weights {w.path} (~{w.size / MIB:,.0f} MiB)")
    print(f"Approximate total: {total / 2**30:.1f} GiB")
    if not yes and input("Proceed? [y/N] ").strip().lower() != "y":
        raise SystemExit("Nothing was downloaded.")
    for s in todo_src:
        path = GPU / s.name
        if not path.exists():
            run(["git", "clone", s.url, str(path)])
        run(["git", "-C", str(path), "fetch", "--depth", "1", "origin", s.commit])
        run(["git", "-C", str(path), "checkout", "--detach", s.commit])
    for env in todo_env:
        version, reqs, _ = ENVS[env]
        if not python_of(env).is_file():
            run(["uv", "venv", "--python", version, str(GPU / env)])
        pip = ["uv", "pip", "install", "--python", str(python_of(env))]
        run([*pip, "--index-strategy", "unsafe-best-match", "-r", str(reqs)])
        if env == "main-env":
            run([*pip, "--no-deps", "-e", str(GPU / "fast3r-src")])
            # SAM 2's optional CUDA post-processing extension needs nvcc; it is not required.
            env_vars = {**os.environ, "SAM2_BUILD_CUDA": "0"}
            run(
                [*pip, "--no-deps", "--no-build-isolation", "-e", str(GPU / "sam2-src")],
                env=env_vars,
            )
    for w in todo_w:
        download(w)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="Verify only; change nothing.")
    ap.add_argument(
        "--profile",
        choices=["local", "clg", "all"],
        default="local",
        help="Which model weights to install/check (default local).",
    )
    ap.add_argument("--hash", action="store_true", help="Also verify weight checksums (slow).")
    ap.add_argument("--yes", action="store_true", help="Do not ask before downloading.")
    args = ap.parse_args()
    if not args.check:
        install(args.profile, args.yes)
    problems = check(args.profile, verify=args.hash)
    for problem in problems:
        print("PROBLEM:", problem)
    if problems:
        return 1
    print(f"GPU runtime OK for profile '{args.profile}'. The worker finds var/gpu by itself;")
    print("override with NAZAR_GPU_PYTHON / NAZAR_SPLAT_PYTHON / NAZAR_GPU_WEIGHTS if needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
