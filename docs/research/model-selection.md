# Geometry model selection (Milestone 3)

_Checked 2026-10-27 against the official repositories. Nothing has been downloaded; no weights are on disk._

**Verified** means read on the official repository page on that date. **Hypothesis** means expected and not measured. Re-check licence terms before deploying, because they change (VGGT changed its licence in 2026).

## Matrix

| Candidate | Role | Source | Licence (code / weights) | Hardware | Input → output | Restrictions | Adapter | Measured on our sample |
|---|---|---|---|---|---|---|---|---|
| **OpenCV SfM baseline** (built) | CPU geometry fallback; always available | `opencv/opencv-python` 5.0, `scipy` 1.18 | Apache-2.0 / BSD-3. No weights. SIFT's patent has expired and it ships in main OpenCV. | CPU only | Keyframe JPEGs → sparse coloured points, camera poses, focal length (shared, estimated) | Sparse output. Needs parallax: a pure rotation or a hover yields nothing, and the job fails with a reason. Local frame, unknown scale. | `apps/worker/src/nazar_worker/sfm.py` + `baseline.py` | sample1: 22/22 keyframes registered, ~6.4k points, mean reprojection 0.63 px, first preview ≈ 8–13 s, total ≈ 18 s on the laptop CPU |
| **Fast3R** (named in the brief) | Primary GPU geometry: poses + dense pointmaps in one pass | [facebookresearch/fast3r](https://github.com/facebookresearch/fast3r); weights on Hugging Face `jedyang97/Fast3R_ViT_Large_512` | **FAIR Noncommercial Research License**, covering code and models (verified). The repository is **archived** (read-only). | CUDA GPU. The README gives no VRAM figure. It installs with CUDA 12.4 and has a no-FlashAttention fallback. Hypothesis: ViT-L at 512 px with tens of frames needs well over 6 GB, so plan on the college GPU. | Image list → per-view pointmaps + confidence, poses | Non-commercial only. Archived, so no upstream fixes. | Not written yet (`StageAdapter` for `geometry`) | Not run (needs C1 approval + GPU) |
| **VGGT** | Alternative feed-forward geometry (cameras, depth, points, tracks) | [facebookresearch/vggt](https://github.com/facebookresearch/vggt) | Code: commercial-friendly licence (LICENSE.txt). Weights: the original checkpoint is **non-commercial**. `VGGT-1B-Commercial` is **gated behind an application form**, and commercial use excludes military applications (verified). | CUDA GPU. No absolute VRAM figure is published. A 2026 update claims 2–3× more frames for the same memory. | Images → cameras, depth maps, point maps, tracks | Gated weights; the military-use exclusion matters for a drone project and should be checked against the intended use. | Not written | Not run |
| **MASt3R** (DUSt3R family) | Alternative pairwise matching + global alignment | [naver/mast3r](https://github.com/naver/mast3r) | **CC BY-NC-SA 4.0** for code and checkpoints, **plus the licences of every training dataset** (some, such as Map-free, are "very restrictive") (verified) | CUDA GPU. Pairwise, so cost grows with the number of pairs. | Image pairs → pointmaps, matches; sparse global alignment | Non-commercial + share-alike + dataset terms | Not written | Not run |
| **COLMAP** | Classical reference/validator (better BA and matching than our baseline) | [colmap/colmap](https://github.com/colmap/colmap) | New BSD (verified). Third-party dependencies are licensed separately and can change the licence of the built binary. | CPU; GPU SIFT optional | Images → sparse/dense model | Native binary to install; heavier ops footprint | Not written. A good candidate to *validate* GPU outputs. | Not run |

## Decision so far

- **Default today:** the OpenCV baseline. It is the only option whose licence needs no approval and that runs on the laptop. It is labelled "CPU baseline · sparse SfM" in the UI and in every artifact's provenance (`producer: nazar-worker/sfm-baseline`).
- **Proposed GPU primary:** Fast3R, as the brief asks, **for non-commercial academic use only**. Its archived state is a risk; VGGT is the fallback if Fast3R cannot run within the college GPU budget.
- **Needs you (C1 in `PENDING_USER_TESTS.md`):** confirm that the project is non-commercial academic work, so that the FAIR NC and CC BY-NC-SA terms are acceptable. Until then, no weights are downloaded.

## How the baseline works (for the report)

1. SIFT features (4000 per keyframe, 640 px keyframes).
2. Mutual ratio-test matching within a window of 12 keyframes, then essential-matrix RANSAC.
3. Union-find tracks.
4. Choose the initial pair. Reject near-homographies (planar or rotation-only) and require ≥ 2° median parallax.
5. Incremental PnP registration (EPnP + LM refinement).
6. Triangulate with ≥ 1.5° parallax, ≤ 4 px error and positive depth.
7. Sparse bundle adjustment: analytic Jacobian, Huber loss, shared focal length. The analytic Jacobian is checked against finite differences to 1e-8.
8. Prune, normalise to median camera distance = 10 (unitless), then level the scene with a RANSAC plane fit.
9. A point is **Observed** when seen in ≥ 3 views with ≤ 1 px error, otherwise **Estimated**. The report records the rule.
