# 06 — Full backend pipeline: implementation plan

_Status: plan only, nothing implemented yet. Written 2026-11-03. Supersedes the order and several snippets in guides 01–04 (corrections are listed in section 9)._

## 1. Goal of this iteration

Give the backend **one video** and get back **one explainable 3D model** (a solid, coloured mesh, plus a splat scene on the college GPU), where **every model contributes something we can point at**:

| Model | What it contributes to the final model | How we show it |
| --- | --- | --- |
| YOLO11 + SAM 2 | Removes moving cars/people so they do not smear the model | Mask overlays, count of removed points |
| Fast3R | Camera poses and the dense base geometry | Points, camera path |
| Metric3D-v2 | Surface normals and extra depth in textureless areas (roads, roofs) | Points tagged `source=depth`, normal-agreement stats |
| GNSS Sim(3) (existing) | Metric scale and UTM placement, when telemetry exists | `sensor_alignment` in the report |
| Open3D | Fuses, cleans and turns points into a mesh | Mesh stats, inferred-surface share |
| 3D Gaussian splat | Photoreal view of the same scene | Held-out-view quality number |

The entry point is a backend-only test script, not the web UI.

## 2. Two run modes only

| | `local` | `clg` |
| --- | --- | --- |
| Hardware | RTX 4050 Laptop, 6 GB VRAM, Windows | College VDI, Linux, 30+ GB VRAM |
| Rule | **Peak GPU memory stays under 6 GB. Slow is fine.** | Use the headroom for quality and fewer passes |
| Execution | One model at a time, each in its own process that exits (frees VRAM) before the next starts | Same sequence, bigger settings |
| Fast3R | ~9 views/pass, chained passes (as today) | Most or all keyframes in 1–3 passes |
| SAM 2 / Metric3D | Small variants, one image at a time, reduced resolution | Larger variants, batches, full resolution |
| Splat | Reduced resolution, capped Gaussian count, fewer iterations | Full resolution and iterations |

How the profile is applied:
- A `ComputeProfile` object (`local` / `clg`) holds every size knob (views per pass, model variant, resolution, batch size, iterations, VRAM budget). Stages read it; nothing is hard-coded per stage.
- **Local budget enforcement:** each runner sets `torch.cuda.set_per_process_memory_fraction` so it cannot exceed the budget (about 5.5 GiB of the 6 GiB, leaving room for the desktop), reports `torch.cuda.max_memory_allocated()` after its stage, and on out-of-memory shrinks its own batch/resolution and retries (bounded). The report records the real peak per stage, so "within 6 GB" is measured, not claimed.
- The existing Windows note stays: the runner also needs ~5–8 GiB of free system commit.
- `clg` is selected explicitly. Nothing silently switches between the two.

## 3. Pipeline order (sequential, each stage feeds the next)

```
video
 1. preprocessing   FFmpeg/OpenCV  -> keyframes (existing)
 2. dynamic         YOLO11 + SAM 2 -> per-keyframe masks of moving objects
 3. geometry        Fast3R         -> poses + pointmaps (masked pixels dropped)   [existing, extended]
 4. depth_priors    Metric3D-v2    -> depth + normals, aligned to Fast3R's scale
 5. sensor          Sim(3) GNSS    -> metric scale / UTM (only with telemetry)    [existing]
 6. dense           Open3D         -> fuse Fast3R + depth points, clean, normals
 7. surface         Open3D Poisson -> coloured mesh with per-vertex confidence
 8. splat           3DGS           -> Gaussian scene (see 6)
 9. analysis        confidence + per-model contribution summary
10. export          PLY, LAS, GLB (points), GLB (mesh), splat, report
```

**Contract change (needs your OK):** today `dynamic_analysis` runs *after* `geometry`, so masks could only delete points and could not improve poses. Moving it before `geometry` means editing `StageName` / `PIPELINE_STAGES` in `packages/contracts`, regenerating the TypeScript, and updating the web stage list and tests. I recommend doing it.

## 4. Explainability (built in, not added later)

- Every stage returns a small **contribution record** into the report: what it consumed, what it changed, and numbers (points removed, points added, normals changed, residuals, time, peak VRAM).
- Points and mesh vertices carry a **source** tag (`fast3r`, `depth_prior`) and a **confidence** class (observed / estimated / inferred). Poisson surface far from any input point is `inferred`.
- Debug artifacts are published (overlay images of masks, depth/normal previews) so a person can see what each model did.
- The test script has an optional `--ablate` flag that also builds a **Fast3R-only** mesh and prints a side-by-side table, so "does this model help?" has a measured answer.

## 5. Model adapters

Each model follows the Fast3R pattern: its own pinned environment under `var/gpu/`, a runner script in `apps/worker/gpu/`, a `scripts/setup_*.py` with `--check`, a stage adapter in the worker, and a visible skip or fallback with a reason.

- **YOLO11 + SAM 2:** YOLO finds candidate vehicles/people; its boxes prompt SAM 2's *image* predictor per keyframe (keyframes are sparse, so video propagation is a poor fit). Only objects judged moving are masked: a cheap camera-motion-compensated check, and parked vehicles are kept. Masks go to Fast3R's input and are also applied to its output. Holes are labelled, not filled.
- **Fast3R:** extend the runner to accept masks and to output a per-point **view index** (needed so normals can be oriented toward the camera that saw each point).
- **Metric3D-v2:** per-keyframe depth + normals at a resolution that fits the profile; scale-fit each depth map to Fast3R's geometry; reject pixels that disagree; add points only where Fast3R is empty. Intrinsics are Fast3R's estimate, so "metric" stays labelled *estimated*.
- **Open3D (CPU, in the worker env):** fuse, outlier removal, normals oriented per point toward their camera, Screened Poisson, density trim, largest components, vertex colours and confidence. Mesh GLB is written with our own numpy writer (`glb.py`, new TRIANGLES primitive), not Open3D's file writer.
- **Splat:** InstantSplat as published initialises from DUSt3R/MASt3R (different licence, heavy). Plan: write a converter from Fast3R poses + points into a 3DGS training setup and train with either InstantSplat's loop or `gsplat` (decided by a spike, section 7). On `local` it runs at reduced settings inside the 6 GB budget; if that does not fit, the stage skips with a reason and `clg` is the supported path.

## 6. The test script

`scripts/test_pipeline.py --video PATH --how local|clg [--telemetry PATH] [--ablate] [--out DIR]`

- Runs the whole pipeline **in-process with no API/web**: preflight and keyframes from `packages/media`, then the same stage adapters through a small local client (like the existing `BundleClient`, writing artifacts to `--out`).
- `--how` picks the `ComputeProfile`.
- Output folder: all artifacts, `report.json`, mask/depth preview images, and a printed summary: per-stage time, peak VRAM against the budget, per-model contribution, final counts. It exits non-zero if a stage fails or the local VRAM budget is exceeded.
- Pytest wrapper marked as a GPU/integration test; it never runs in the fast suite.

## 7. Work breakdown (branch + push)

- Branch: `feature/full-pipeline`, created from `main`. Remote `origin` is `github.com/kage-zero/nazar`.
- One commit per finished part, pushed after each, in this order. Each part ends green on its tests and updates `docs/IMPLEMENTATION_STATUS.md`.

1. **Profiles + stage order:** `ComputeProfile`, contract reorder (dynamic before geometry), per-stage peak-VRAM reporting, contribution records in the report.
2. **Test script skeleton:** local client, `--video/--how`, runs today's pipeline end to end and prints the summary.
3. **Open3D fuse + mesh (CPU):** view-index plumbing, per-point-camera normals, Poisson, confidence, mesh GLB, tests.
4. **YOLO11 + SAM 2:** runner, setup script, masks into Fast3R, overlay artifacts.
5. **Metric3D-v2:** runner, scale fit, normals into the mesh, extra points, ablation.
6. **Splat:** spike first (what fits in 6 GB, which trainer), then adapter and `clg` run.
7. **Web viewer:** mesh layer and toggles (secondary to the backend goal; after the above).

Each model part starts with a **spike**: install, run on sample1, record peak VRAM and time on the 6 GB laptop *before* writing the adapter.

## 8. Decisions I need from you

1. **Stage reorder** (dynamic before geometry): OK?
2. **YOLO licence:** Ultralytics YOLO11 is AGPL-3.0. OK for this academic project, or use another detector?
3. **Weights/licences to approve before any download:** SAM 2 (believed Apache-2.0), Metric3D-v2 (believed BSD-2; not verified here), and the splat trainer. I will re-check each repo's licence and report before downloading.
4. **Splat on `local`:** if it cannot fit 6 GB even at reduced settings, is "clg only" acceptable for that one stage?
5. **Push:** pushing to `origin` (`kage-zero/nazar`) after each part, as you asked. Confirm that is the right remote.

## 9. Corrections to guides 01–04 (to apply)

- 01: orient normals per point (not toward the mean camera); mesh the filtered cloud; use `skip_reason()` instead of an early return; apply `metres_per_unit`; the `<primitive>` + child material pattern does not work; the viewer needs store/job-state wiring.
- 02: `run.depth_maps`, `run_metric3d_inference`, `serialize_depth_maps` do not exist; the Metric3D call signature must be checked against the real repo; depth needs intrinsics and a scale fit.
- 03: SAM 2 is built but never called; the stage order contradicts the diagram; parked vehicles must not be masked blindly.
- 04: InstantSplat does not take Fast3R output directly; the "under 60 seconds" figure is for a few views; licence line is unverified.

## 10. Honest unknowns (measured in the spikes, not assumed)

- Whether Metric3D's large model fits in 6 GB at useful resolution (may need tiling or the small variant).
- Whether any 3DGS training fits in 6 GB at useful quality.
- Whether masking measurably improves the samples (they may contain few moving objects).
- Whether Poisson alone gives a clean surface on the Colosseum and pyramid clips; if not, TSDF fusion from per-view depth is the fallback.
- Open3D wheel compatibility with the worker's `numpy>=2.3` pin on Python 3.12.
