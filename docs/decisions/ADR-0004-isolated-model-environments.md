# ADR-0004: Research models run in isolated, pinned environments behind file contracts

- **Status:** Accepted (2026-10-26). The per-model pins are not chosen yet (Milestone 1/3).

## Context

Fast3R, Metric3D-v2, SAM2, YOLO, InstantSplat, SuGaR and GTSAM have different and partly conflicting Python/PyTorch/CUDA/compiler requirements. Putting them all in one environment is the main integration risk the project brief calls out.

## Decision

- `apps/worker` (package `nazar-worker`) holds orchestration only and depends on `nazar-contracts`. It does **not** depend on torch or any model.
- Each model stage gets its own pinned environment: a separate uv project or conda env under `apps/worker/models/<name>/`, created on the GPU host only. It is invoked as a subprocess with an explicit input manifest and output directory.
- Adapters (`nazar_worker.stages.StageAdapter`) validate the outputs, write them atomically with sha256 checksums, and return `ArtifactManifest`s.
- At most one heavy GPU stage runs at a time per worker (`NAZAR_GPU_MAX_CONCURRENT_JOBS=1`). Models are loaded per stage and released between stages.
- No weights are downloaded during ordinary tests. CI uses the deterministic test pipeline (`NAZAR_PIPELINE_MODE=test`).

## Amendment (2026-11-04): two GPU environments, not one per model

When every model was integrated, "one environment per model" would have meant four copies of
torch (~2.5 GB each) for models whose requirements turned out to be compatible. The rule is
kept where it matters (the worker never imports torch; every model runs as a subprocess behind
a file contract) but the environments are grouped by *compatible stack*:

- `var/gpu/main-env` (Python 3.11, torch 2.6.0+cu124): Fast3R, Open3D, Ultralytics YOLO,
  SAM 2, Metric3D-v2 (with a tiny `mmcv.utils` stand-in, so no mmcv CUDA build is needed).
  Pinned in `apps/worker/gpu/requirements-main.txt`; sources at fixed commits.
- `var/gpu/splat-env` (Python 3.10, torch 2.4.1+cu124): gsplat 1.5.3, whose prebuilt CUDA
  wheels exist only for that combination (no compiler is needed on Windows or the VDI).
  Pinned in `apps/worker/gpu/requirements-splat.txt`.

`scripts/setup_gpu.py` installs and checks both (and the weights for the `local` or `clg`
profile). Every runner still runs in its own process, one at a time, and exits before the
next starts, so VRAM is released between models. On the `local` profile each process caps its
own allocations (`apps/worker/gpu/_common.py`) and reports its measured peak.

## Consequences

There is extra process overhead per stage, but each adapter can be tested on its own, and a failing model stack can't break the others. Licence and weight terms are checked before anything is downloaded (see `docs/research/`).
