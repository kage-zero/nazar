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

## Consequences

There is extra process overhead per stage, but each adapter can be tested on its own, and a failing model stack can't break the others. Licence and weight terms are checked before anything is downloaded (see `docs/research/`).
