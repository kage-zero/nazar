# NAZAR: complete project documentation

> Single-pass drone video in, an explainable 3D model out. Everything runs on the user's own
> machine; nothing is uploaded to a third party.

_Written 2026-11-16 against branch `feature/splat-quality-and-docs`, which is `feature/frontend-pipeline`
(including the automatic-frame-count and height-map surface commit `1309307`) plus the splat and
fusion quality fixes of §16. Numbers marked **measured** come from real runs on the development
laptop (Windows 11, RTX 4050 Laptop GPU, 6 GB); §17 says which code version each run used.
Anything not measured says so._

## Contents

1. [What NAZAR is](#1-what-nazar-is)
2. [System at a glance](#2-system-at-a-glance)
3. [Repository layout](#3-repository-layout)
4. [Technology stack](#4-technology-stack)
5. [Components in depth](#5-components-in-depth)
6. [Job lifecycle, events and the worker protocol](#6-job-lifecycle-events-and-the-worker-protocol)
7. [The reconstruction pipeline, stage by stage](#7-the-reconstruction-pipeline-stage-by-stage)
8. [Models used](#8-models-used)
9. [Compute profiles, memory budget and time forecast](#9-compute-profiles-memory-budget-and-time-forecast)
10. [Outputs, coordinate frames and confidence labels](#10-outputs-coordinate-frames-and-confidence-labels)
11. [The viewer](#11-the-viewer)
12. [Security model](#12-security-model)
13. [Installation and running](#13-installation-and-running)
14. [Configuration reference](#14-configuration-reference)
15. [Testing and quality assurance](#15-testing-and-quality-assurance)
16. [Quality-tuning history and lessons](#16-quality-tuning-history-and-lessons)
17. [Measured results](#17-measured-results)
18. [Limitations and known issues](#18-limitations-and-known-issues)
19. [Licences](#19-licences)
20. [Troubleshooting](#20-troubleshooting)
21. [Glossary](#21-glossary)

---

## 1. What NAZAR is

NAZAR takes **one video** (typically a drone flight, but any steadily moving camera works) and
produces a **3D reconstruction** of what the camera saw. It reveals the result progressively
while the job runs, and it explains where every part of the model came from.

**Input:** one video file, an optional frames-per-second override (the default is an automatic
frame count), and optional flight telemetry (DJI `.SRT` or `.CSV`).

**Outputs** (all downloadable from the browser):

| Output | Format | What it is |
| --- | --- | --- |
| Photoreal Gaussian splat | `.ply` (3DGS layout) | A view-dependent scene that renders like the video. The closest match to the footage. |
| Solid surface model | `.glb` | A closed, textured solid built from a height map (texture baked from the full-resolution video frames). If a height map is not possible, an Open3D Poisson mesh with per-vertex colour is produced instead. |
| Point cloud | `.ply`, `.las`, `.glb` | The fused, filtered, coloured dense cloud. |
| Camera path | `.json` | Refined camera poses per keyframe. |
| Moving-object masks | `.zip` | Masks for people/vehicles that were excluded. |
| Depth previews | `.zip` | Metric3D depth maps as images. |
| Splat held-out renders | `.zip` | Photo vs. render for held-out views. |
| Processing report | `.json` | Every parameter, timing, peak GPU memory, per-model contribution, limitation. |

**Design principles** (these shape many decisions below):

- **Honesty over polish.** Output is labelled `local_reconstruction` with an unknown scale unless
  there is evidence for more. Nothing is called metric, georeferenced or "observed" without a
  stated basis. Model confidence is the model's own score, not a measured error.
- **Local-first.** API, web app, worker and models all run on one laptop. A second location
  (a college GPU) can run the same worker over HTTPS.
- **Progressive.** The first point cloud appears within seconds; later stages replace it in place.
- **Explainable.** Each model's contribution, memory use and any skip reason is recorded.
- **Bounded.** A hard GPU memory budget (5.5 GB on the laptop) is enforced per model process.

---

## 2. System at a glance

```text
 Browser (React 19 + React Three Fiber)        API tier (FastAPI)                 GPU tier (worker + model envs)
 ──────────────────────────────────────       ───────────────────                ─────────────────────────────────
 apps/web  ── REST /api/* ──────────────────▶ apps/api                  ◀─ HTTPS ─ apps/worker  (nazar-worker run)
           ◀─ WebSocket job events ───────────  │ SQLite (default) / PostgreSQL     │ leases jobs (pull model)
           ◀─ artifact bytes (authorised) ────  │ local filesystem / S3 (MinIO)     │ posts events, uploads artifacts
                                                ▼                                   ▼
                                       packages/contracts                 per-model Python processes
                                       (Pydantic → JSON Schema → TS)      (isolated environments, JSON-lines
                                                                           events on stdout, files on disk)
```

**Key ideas**

1. **Pull-based GPU worker (ADR-0003).** The worker polls the API for a lease, so the GPU
   machine needs no inbound port. The same worker runs on the laptop or on the college VDI.
2. **Isolated model environments (ADR-0004).** Fast3R, SAM 2, Metric3D, YOLO, Open3D and gsplat
   have conflicting dependencies. Each runs in its own pinned virtual environment, started by the
   worker as a subprocess behind a file contract. The orchestrator never imports torch.
3. **Event-sourced job state.** The API keeps an append-only event log; job status and per-stage
   state are derived from it by one state machine, so a replay rebuilds the same snapshot.
4. **Generated contracts.** Pydantic models are the single source of truth. They generate a JSON
   Schema and the TypeScript types the web app uses, with a drift check in CI.

---

## 3. Repository layout

```text
apps/
  web/                 React 19 + TypeScript + Vite + R3F + Tailwind v4 + Zustand (the UI)
  api/                 FastAPI service: auth, missions, uploads, preflight, jobs, worker routes
  worker/              Reconstruction worker CLI + stage adapters + GPU runner scripts
    src/nazar_worker/  orchestration, fusion, georef, exports, forecast, profiles
    gpu/               scripts run INSIDE the model environments (one per model/step)
packages/
  contracts/           Pydantic contracts → JSON Schema → generated TypeScript
  media/               FFmpeg probe/decode, frame metrics, keyframe selection, telemetry parsing
scripts/               init_env.py, setup_gpu.py, test_full_pipeline.py, run-college-worker.sh
infra/                 optional docker-compose (PostGIS, Redis, MinIO)
docs/                  brief, design guide, ADRs, research notes, this document
var/                   git-ignored runtime data (storage, model envs + weights, run outputs)
run-local.bat          API + web + local-GPU worker on this laptop, opens the browser
run-college.bat        API + web only, for the college GPU (online or bundle mode)
```

Workspaces: pnpm 12 + Turborepo 2 for the JavaScript side, a uv workspace (Python 3.12) for the
Python side.

---

## 4. Technology stack

| Layer | Technology |
| --- | --- |
| Web | React 19.3, TypeScript 6, Vite 8, Tailwind CSS 4.3, Zustand 5, three 0.186, React Three Fiber 9.8, drei 10.7, **Spark 2.4.0** (Gaussian splat renderer, lazy chunk), Vitest 5, Playwright 1.64 |
| API | Python 3.12, FastAPI, Uvicorn, SQLAlchemy 2, Alembic (5 migrations), pydantic-settings; SQLite by default, PostgreSQL/PostGIS optional |
| Contracts | Pydantic → JSON Schema → TypeScript (generated), drift-checked |
| Media | FFmpeg/ffprobe (argv calls, no shell), OpenCV, NumPy, SciPy |
| Worker (orchestrator) | Python 3.12, NumPy, SciPy, OpenCV; no torch |
| Main GPU env | Python 3.11, torch 2.6.0+cu124, Fast3R, SAM 2, Metric3D-v2, Ultralytics YOLO, Open3D 0.20 |
| Splat env | Python 3.10, torch 2.4.1+cu124, gsplat 1.5.3 |
| Tooling | uv, pnpm, Turborepo, Ruff, ESLint, Prettier, mypy/tsc |

---

## 5. Components in depth

### 5.1 Web app (`apps/web`)

A single-page app with a mission panel, a run screen and a 3D viewer.

- **Auth.** First-run operator setup (loopback only) or sign-in; sign-out.
- **Missions.** Create/select; the selected mission is kept in the URL.
- **Upload.** Chunked XHR upload with byte progress, cancel, automatic retry with backoff and
  resume (re-choose the same file). Validation progress is shown by phase.
- **Preflight panel.** Duration, resolution, frame rate, codec, rotation, usable frames,
  keyframes, findings by severity (blurry, dark, over-exposed, repeated, low resolution, little
  camera movement, no telemetry), a sharpness-over-time chart, a keyframe strip and table.
- **Telemetry box.** Attach/remove a DJI `.SRT` or `.CSV`; shows samples, gaps, coverage.
- **Run setup.** "Run on" (Local GPU / College GPU); **frame count: automatic by default**
  (about one frame per second of video, at least 24, at most 40 local / 96 college), or a manual
  **frames per second** (slider, number box, presets 0.5/1/2/4) with a live frame-count and time
  estimate; and a readiness list of the models on the selected worker.
- **Run screen.** Step _N of 7_, current model, counts ("frame 12 / 23", "iteration 2,000 /
  2,500"), elapsed clock, a time-left range and the basis of the estimate, per-stage cards with
  forecast vs. real time and GPU peak vs. budget, and a plain reason for any skipped stage.
- **Contributions.** After completion: what each model contributed (masks, poses, depth, fusion,
  splat PSNR, mesh share inferred) from `report.json`.
- **Outputs.** Download list for every artifact.
- **Completion feedback.** Optional sound/vibration, once per watched job.

Libraries under `src/lib` (sampling, estimate, contributions, jobStream/jobState reducers,
measure, provenance, telemetry, upload, viewHome …) are unit-tested with Vitest.

### 5.2 API (`apps/api`)

| Area | Routes (all under `/api`) |
| --- | --- |
| System | `GET /health`, `GET /ready` (database, storage, secrets, operator account, worker contact, GPU runtime) |
| Auth | `GET /auth/state`, `POST /auth/setup`, `/auth/login`, `/auth/logout` |
| Missions | `GET/POST /missions`, `GET /missions/{id}`, `POST /missions/{id}/assets` |
| Assets | `PUT /assets/{id}/content?offset=N` (resumable), `GET/DELETE /assets/{id}`, `POST /assets/{id}/retry`, `GET /assets/{id}/preflight`, `GET /assets/{id}/{kind}/{n}.jpg`, `GET /assets/{id}/telemetry` |
| Jobs | `POST/GET /missions/{id}/jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/events?after=N`, `POST /jobs/{id}/cancel`, `/retry`, `WS /jobs/{id}/stream?after=N`, `GET /artifacts/{id}/content` |
| Worker (bearer token + lease header) | `POST /worker/lease`, `/jobs/{id}/heartbeat`, `/jobs/{id}/events`, `GET /jobs/{id}/inputs/{preflight,keyframes/{n}.jpg,telemetry,video}`, `POST /jobs/{id}/artifacts`, `PUT /jobs/{id}/artifacts/{aid}/content` |

Uploaded video is hashed (SHA-256) and validated on one background thread: ffprobe, a full
decode at 320 px, per-frame sharpness / exposure / change / motion / viewpoint signature,
keyframe selection, full-resolution and thumbnail JPEGs, and an atomic `preflight.json`.
Assets left `validating` by a restart are re-queued on startup.

### 5.3 Contracts (`packages/contracts`)

Pydantic models for the job state machine, events, artifact manifests, health/readiness, auth,
missions, assets, the preflight report, telemetry summaries and the worker protocol. Constants
shared with the browser include the stage order, transition table and sampling limits:
`FPS_MIN 0.25`, `FPS_MAX 4`, `FPS_DEFAULT 1`, `MIN_FRAMES 3`, manual-mode `MAX_FRAMES` 64 (local) /
128 (college), and automatic mode `AUTO_MIN_FRAMES 24`, `AUTO_MAX_FRAMES` 40 (local) / 96 (college).

### 5.4 Media (`packages/media`)

FFmpeg probe (rotation, display size, VFR detection from packet timestamps), single-pass decode,
per-frame quality metrics, keyframe selection by viewpoint novelty (min/max gap,
sharpest-in-look-ahead, cap 96), per-job **frame sampling** (the sharpest usable frame per time
window, for the chosen fps or the automatic count), and the telemetry parsers (DJI SRT in three layouts, Airdata CSV,
plain CSV; ENU conversion via WGS84 ECEF; dropped samples counted, never repaired).

### 5.5 Worker (`apps/worker`)

`nazar-worker` commands: `doctor` (read-only GPU/disk/toolchain report), `stages`, `run` (job
loop), `local` (whole pipeline in-process on one video, no API or web app; writes artifacts and a
summary). `run` leases a job, starts a heartbeat thread, runs the stage adapters, posts events
and uploads artifacts, and handles cancel, lost lease and failure. Modes: `test` (synthetic
plumbing pipeline, always labelled synthetic) and `standard` (the real pipeline below).

---

## 6. Job lifecycle, events and the worker protocol

**State machine:** `created → validating → queued → preprocessing → geometry → depth_priors →
dynamic_analysis → sensor_optimization → dense_reconstruction → surface_processing → analysis →
exporting → completed`. Optional stages may be skipped (reported with `stage.skipped` and a
reason, never as completed). Any non-terminal state can go to `failed` or `cancel_requested`;
`failed`/`cancelled` can return to `queued` (retry). `completed` is reachable only from
`exporting`.

(The worker runs dynamic analysis _before_ geometry so masks can be applied; the UI presents the
steps in processing order.)

**Event envelope:** `schema_version`, `job_id`, `seq` (per-job cursor), `ts`, `status`, `stage`,
`type`, typed `data`. Types: `job.created`, `job.queued`, `job.estimate`, `stage.started`,
`stage.progress` (counts only when real work is countable), `stage.completed`, `stage.skipped`,
`warning`, `artifact.available`, `preview.updated`, `job.completed`, `job.failed`,
`cancel.requested`, `job.cancelled`.

**Event log:** append-only; `seq` from an atomic `UPDATE … RETURNING`; unique per-job
idempotency keys; status derived by replay.

**Worker protocol:** lease (`POST /worker/lease` with `NAZAR_WORKER_TOKEN`), heartbeat, event
batches, input downloads, artifact uploads, all carrying `X-Nazar-Lease`. A lost lease returns
409 and the worker drops the job; a sweeper re-queues expired leases with `attempt + 1`.

**Artifacts:** the worker declares a manifest (kind, revision, media type, size, SHA-256, frame,
bounds, source frames, provenance), then PUTs bytes. The API checks size and hash before an
atomic rename and emits `artifact.available` (and `preview.updated` for point clouds).

**Browser stream:** snapshot over REST, then `WS /jobs/{id}/stream?after=N`; on any close the
client catches up over REST and reconnects with backoff. The client reducer mirrors the server's
state machine and reloads the snapshot on a gap.

---

## 7. The reconstruction pipeline, stage by stage

```text
video ─▶ [1 Preprocess] ─▶ [2 Moving objects] ─▶ [3 Geometry] ─▶ [4 Depth priors]
                                YOLO11 + SAM 2       Fast3R           Metric3D-v2
                                                                          │
   [5 GNSS alignment] (telemetry only, else skipped) ◀────────────────────┤
                                                                          ▼
   [6 Dense scene: fusion ─▶ Gaussian splat (gsplat)] ─▶ [7 Surface: Poisson mesh (Open3D)]
                                                                          │
                                            [8 Analysis] ─▶ [9 Export] ◀──┘
```

The UI groups these as "Step N of 7". Intermediate results are published as they appear
(preview point clouds, then the final cloud, then splat and mesh).

### 7.1 Preprocessing

Fetches the keyframes selected at upload (quality + viewpoint novelty). The per-job frame choice
re-samples the video: the sharpest usable frame in each time window. **Automatic mode** asks for
about one frame per second, never fewer than 24 (a 6 s clip is sampled at ~4 fps rather than
reduced to 6 views) and never more than 40 (local) / 96 (college). **Manual mode** uses the
chosen fps, capped at 64 (local) / 128 (college); below 3 frames the API returns 422. Frames are
decoded for the runners.

### 7.2 Moving-object analysis (`dynamic_runner.py`)

1. **YOLO11** proposes candidates of movable classes (person, bicycle, car, motorcycle, bus,
   truck, boat).
2. A detection counts as _moving_ only with evidence: neighbouring keyframes are registered with
   a ground-plane homography (ORB + RANSAC, detections excluded), the box is projected into them,
   and the object must have left that spot. Parked vehicles are therefore kept; objects with no
   usable neighbour are "unknown" and not masked.
3. **SAM 2** turns each moving object's box into a pixel mask.

Masked pixels get minimum confidence in Fast3R, are excluded from fusion, and are excluded from
the splat's photometric loss. Outputs: `masks/NNNN.png`, debug overlays, `objects.json`.

### 7.3 Geometry (`fast3r_runner.py`, `fast3r.py`)

**Fast3R** (ViT-L/512, bf16) predicts per-view pointmaps with confidence, a focal length and
camera poses in one feed-forward pass. On a 6 GB card only a few views fit at once, so frames
run in **overlapping passes**; each pass is aligned to the frames already placed with a
similarity transform (scale, rotation, translation) fitted on the overlapping views (an
overlapping view appears in both passes at identical pixels, giving dense correspondences). Pass
size is chosen from free VRAM inside the budget and shrinks automatically after an out-of-memory
retry. Output: `result.npz` with points, confidence, RGB, poses, focal, crop info and the
moving-object flags.

Points below `max(KEEP_MIN_CONF, job's KEEP_QUANTILE percentile)` of confidence are dropped; kept
points above `OBSERVED_MIN_CONF` are labelled _observed_, the rest _estimated_ (heuristic labels
from the model's own score). The cloud is moved into NAZAR's frame (+Y up by levelling the
dominant plane, centred, scaled so the median camera distance is 10 units). If Fast3R is
unavailable or fails, the job still completes with the **CPU baseline** (classical SfM:
SIFT + essential matrix + PnP + bundle adjustment) and a visible `fast3r_fallback` warning.

### 7.4 Depth priors (`metric3d_runner.py`)

**Metric3D-v2** produces depth and surface normals per keyframe (largest model that fits the
budget: ViT-Large locally, ViT-Giant2 on the college GPU). Depth is scaled for the given
intrinsics (Fast3R's estimated focal length), so anything derived is labelled _estimated_.
Output: per-frame `NNNN.npz` (depth f16, normals f16 in OpenCV camera axes, normal confidence)
and depth preview PNGs.

### 7.5 Sensor optimisation (`georef.py`, telemetry only)

If telemetry was attached, a Umeyama Sim(3) fit maps camera centres to GNSS positions (searching
a ±2 s clock offset, one outlier-rejection pass). **Scale** needs ≥ 5 matched keyframes, ≥ 50 %
of placed keyframes matched, a baseline ≥ 20 m and RMS residual ≤ max(3 m, 5 % of the
baseline). **Orientation** additionally needs altitude and a non-degenerate path. UTM is
computed in-house (Krüger series). Without telemetry the stage is skipped with a reason.

### 7.6 Dense scene (`fusion.py`, `splat_runner.py`)

**Fusion (CPU, NumPy).** Fast3R pointmaps are combined with the Metric3D priors:

- **Scale evidence:** per view, the median ratio of Fast3R camera depth to Metric3D depth gives
  units-per-metre; the spread across views measures consistency. Reported, **never applied**
  (it inherits Fast3R's focal error; on `sample1` it was ~2.2× off the true size).
- **Normals:** each fused point carries its pixel's Metric3D normal rotated into the world frame.
- **Fill (strict):** low-confidence pixels may be filled from the scaled prior depth only if the
  view's prior agrees with Fast3R (median relative error ≤ 0.15), the depth is inside the range
  Fast3R observed, **real Fast3R points surround the pixel (≥ 20 % of a 15×15 window), the prior
  depth is within 8 % of the neighbouring Fast3R depth, and the pixel is not sky-coloured.**
  Filled points are tagged `depth_prior`.
- **Grazing-angle filter:** Fast3R points on surfaces seen nearly edge-on (|cos| between the
  prior normal and the viewing ray < 0.2) are dropped; they stretch into sparse stripes that
  never mesh cleanly.
- **Moving objects** are excluded everywhere.
- A voxel reduction caps the cloud (600k points local, 2M college), then a statistical outlier
  filter removes strays.

**Gaussian splat (`splat_runner.py`, gsplat 1.5.3).** Following InstantSplat, Gaussians start on
the dense fused cloud (not random points or COLMAP) and are optimised **together with the camera
poses** against the keyframes:

- **Initial Gaussians:** up to 400k seeded from the cloud, isotropic at the local point spacing.
- **Adaptive densification:** gsplat's `DefaultStrategy` splits/duplicates Gaussians where the
  image gradient says detail is missing and prunes transparent or oversized ones, with a periodic
  opacity reset. Growth runs for the first 60 % of iterations and stops at the Gaussian cap
  (800k local, 2M college). Thresholds are relative to the **scene extent** (90th-percentile
  radius of the cloud), not the camera path, so clips where the camera barely moves still work.
- **Needle penalty:** a regulariser penalises Gaussians whose longest axis exceeds 4× the
  shortest.
- **Loss:** 0.8 · L1 + 0.2 · (1 − SSIM), masked where moving objects were found.
- **Training images** are shrunk (intrinsics scaled) to at most 1920 px on the long side, so a 4K
  clip does not exhaust GPU memory; 1080p footage is used at full size.
- **Colour:** spherical harmonics, degree stepped up every 1000 iterations to the profile's
  maximum (2 local, 3 college).
- **Poses:** refined jointly after a 200-iteration colour warm-up.
- **Floater clean-up:** after training, Gaussians that are both far from every input point
  (> 20 point spacings) and larger than 5× the median Gaussian are removed.
- **Held-out evaluation:** every 8th keyframe is held out; after a pose-only alignment with the
  Gaussians frozen it is scored (PSNR) and a photo-vs-render image is saved.
- **Memory:** the process caps its own GPU memory to the budget; an out-of-memory error halves
  the Gaussians and retries (up to 3 times).

### 7.7 Surface processing (`heightfield.py`, with `surface_runner.py` as fallback)

One forward pass of aerial video sees the ground and the tops of things from one side, so the
scene is a surface z = h(x, y), not a free-standing object. Poisson meshing of a noisy cloud
turns per-pixel noise into lumps and invents surface where nothing was seen. The default is
therefore a **height-map (DSM) solid** (CPU, NumPy/SciPy/OpenCV, no extra model):

1. **Grid** (`build_grid`): fused points (+Y up) are binned on the ground plane; each cell keeps a
   high percentile of its heights (the visible top, robust to floaters); isolated spikes are
   removed; small holes are filled by normalised convolution and labelled _inferred_; heights are
   smoothed with an edge-preserving filter so real walls survive.
2. **Texture** (`bake_texture`): every texel of a top-down texture is a 3D point on the surface;
   it is projected into each full-resolution frame, checked for occlusion against a depth buffer
   of the surface, and coloured from the frames that see it best (steeper angle, closer, away
   from the border), blended softly so seams are hidden without averaging misregistered views.
3. **Mesh** (`build_mesh`): the grid becomes triangles, closed into a solid block (side walls and
   a flat base) with planar UVs into the texture. The GLB is exported with an unlit textured
   material so the viewer does not re-shade the photograph.

If the scene cannot be turned into a height map (for example too sparse or mostly unobserved),
the stage warns (`surface_heightfield_unavailable`) and falls back to **Open3D screened Poisson**
(`surface_runner.py`): normals from Metric3D where available, Poisson depth 10, trimming of
low-density vertices (10th percentile) and of anything farther than 6 point spacings from the
data, removal of small pieces, Taubin smoothing (40 iterations), quadric decimation to 1.2M
triangles, and per-vertex colour with a confidence class (_observed_, _estimated_, _inferred_ when
bridging more than 2.5 spacings from any data). The fallback has no texture.

What the surface cannot do: show what no frame saw. Vertical faces become steep slopes and the
unseen far side is simply not there.

### 7.8 Analysis and export

**Analysis** counts observed/estimated points, warns that scale is unknown (or reports the GNSS
scale and its limits), lists the models that contributed and states that learned geometry is
predicted. **Export** writes the point cloud (PLY, LAS, GLB), mesh GLB, splat PLY, camera
trajectory, renders and the report. With accepted telemetry the LAS is written in metres (UTM if
orientation was also accepted); otherwise in local axes.

---

## 8. Models used

| Model | Role | Where it runs | Size / memory | Licence |
| --- | --- | --- | --- | --- |
| **Fast3R** ViT-L/512 (`jedyang97/Fast3R_ViT_Large_512`) | Poses + dense pointmaps from many views in one pass | main env, GPU, bf16 | ≈ 1.2 GiB weights + ≈ 215 MiB per 512×288 view; measured peak ≈ 5.1 GB for 16 views | **FAIR Noncommercial Research** (academic use only); repo archived |
| **YOLO11** s (local) / x (college) | Candidate moving objects | main env, GPU | small / 114 MB weights | AGPL-3.0 (Ultralytics) |
| **SAM 2.1** hiera-small (local) / large (college) | Pixel masks for moving objects | main env, GPU | ~180 MB / 898 MB | Apache-2.0 |
| **Metric3D-v2** ViT-Large (local, fallback ViT-Small) / ViT-Giant2 (college) | Metric depth + surface normals | main env, GPU | ViT-L ≈ 4.3–5.0 GB peak measured; Giant2 weights 5.5 GB | BSD-2-Clause |
| **gsplat 1.5.3** | Differentiable Gaussian rasteriser + densification strategy | splat env, GPU | ≈ 1–1.5 GB peak measured | Apache-2.0 |
| **Open3D 0.20** | Poisson fallback meshing, smoothing, decimation | main env, CPU | n/a | MIT |
| **Spark 2.4.0** | In-browser Gaussian splat renderer | browser (WebGL2) | lazy chunk | MIT |
| OpenCV, SciPy, NumPy | SfM baseline, homographies, KD-trees, geometry | worker / runners | n/a | BSD/Apache |

`pnpm gpu:setup` downloads source checkouts at pinned commits and the weights (about 7 GB for the
local profile) into `var/gpu`, after asking for confirmation of the licences.

Model-selection rationale and verified licences are in
[`research/model-selection.md`](research/model-selection.md). Ideas considered but not adopted
(COLMAP as a validator, generative scene completion) are recorded there too.

---

## 9. Compute profiles, memory budget and time forecast

Every size knob lives in `apps/worker/src/nazar_worker/profile.py`; the report records which
profile ran.

| Setting | `local` (RTX 4050 6 GB) | `clg` (college GPU 30+ GB) |
| --- | --- | --- |
| Strict (a failed model fails the job) | no: a step that cannot fit is skipped with a reason | yes |
| GPU budget per model process | 5632 MiB | uncapped |
| Fast3R views per pass | sized from free VRAM | 48 |
| YOLO | yolo11s @ 960 | yolo11x @ 1280 |
| SAM 2 | hiera small | hiera large |
| Metric3D | vit_large → vit_small | vit_giant2 → vit_large |
| Poisson depth (fallback surface) | 10 | 10 |
| Max fused points | 600,000 | 2,000,000 |
| Splat iterations | **2,500** | 15,000 |
| Splat Gaussian cap | **800,000** | 2,000,000 |
| Splat SH degree | **2** | 3 |
| Frames: automatic (min 24) | up to 40 | up to 96 |
| Frames: manual cap | 64 | 128 |

**Memory discipline.** Each runner caps its own PyTorch allocation to the budget and reports its
peak (device-sampled rise over other programs, CUDA context included). Passes shrink and retry
on out-of-memory. Runners exit via `os._exit` after emitting their result because CUDA teardown
can hang on Windows.

**Time forecast** (`forecast.py`): a cost model fitted to measured runs
(fixed ≈ 495 s + per-frame cost), calibrated from stored real durations on the same machine
(splat-less or implausible runs are ignored). The UI shows a range and the basis. The splat term
is `90 s + 0.25 s × iterations` locally.

---

## 10. Outputs, coordinate frames and confidence labels

- **Frame:** right-handed, **+Y up, −Z forward** (OpenGL/three.js). Each adapter converts its
  model's native convention, with a unit test per adapter.
- **Scale:** video-only output is `local_reconstruction` with `scale_status` _unknown_. Metric
  scale is claimed only from accepted GNSS alignment (`metric_sensor`, with `metres_per_unit`).
  Metric3D's implied scale is reported but never applied.
- **Geographic data:** lat/lon are never treated as metres; ENU/UTM conversions record CRS and
  the altitude kind (above take-off / datum not stated / none). No vertical datum is claimed.
- **Confidence classes (points and mesh vertices):** _observed_ (Fast3R confidence above the
  threshold), _estimated_ (kept but lower confidence, or prior-filled), _inferred_ (mesh bridging
  a gap). They are heuristics from the model's own score, not calibrated probabilities.
- **Manifests** carry no paths or credentials; provenance includes whether data came from the
  synthetic test pipeline.

---

## 11. The viewer

React Three Fiber scene with layers, each toggled independently:

- **Photoreal splat** (Spark): the closest match to the video; labelled "front only" because it
  smears off-axis.
- **Solid mesh** (textured height-map solid, or the vertex-coloured Poisson fallback), **Points**, **Colour by confidence**, **Camera path**, **Measure** (relative
  units without GNSS), **Fit**, **Reset view**, optional **Grid**/**Axes** (off by default).
- **Orbit** is limited to ±60° of the side the cameras saw (the far side was never filmed), with
  a **Free orbit** switch and a note saying so.
- Newer revisions swap in place: superseded requests are aborted, the old GPU buffer is
  disposed, and the camera refits only on a job's first cloud or on **Fit**.
- Layers load lazily; the splat module is a separate chunk.

---

## 12. Security model

- One operator account; scrypt password hashes; server-side sessions keyed by the SHA-256 of an
  HttpOnly SameSite=Lax cookie (Secure in production); login throttling per client and email.
- All state-changing requests need `X-Nazar-Request: 1` (CSRF guard); CORS allows that header
  only from configured origins; WebSocket checks origin and cookie.
- Missions are owner-scoped (other owners' ids return 404). Files are stored under
  server-generated ids; uploads are checked for extension and size, hashed, and written atomically.
- Worker routes need the bearer `NAZAR_WORKER_TOKEN` plus a per-lease header. Secrets are
  generated locally into the git-ignored `.env` by `pnpm env:init` (names printed, never values).
- FFmpeg is invoked with argv arrays, never a shell. Telemetry files are parsed as text only.

---

## 13. Installation and running

**Prerequisites:** Node ≥ 22, pnpm, uv, FFmpeg/ffprobe on PATH, and for the GPU pipeline an
NVIDIA GPU with a recent driver (CUDA 12.4 wheels).

```bash
pnpm install
uv sync --all-packages
pnpm env:init            # creates .env and local machine secrets
pnpm gpu:setup           # optional: GPU models into var/gpu (about 7 GB, asks about licences)
pnpm gpu:check           # verify them
```

**Run on this laptop (Windows):** double-click `run-local.bat`. It starts the API
(`127.0.0.1:8000`) and web app (`127.0.0.1:5173`), starts a worker with
`--modes test,standard --location local`, and opens the browser with **Run on → Local GPU**.
First visit: create the operator account.

**Manual:** `pnpm dev` (API + web) and, in a second terminal, `pnpm worker`.

**College GPU:** `run-college.bat` starts API and web only and asks for _Online_ (API opened to
the campus network after confirmation; run `bash scripts/run-college-worker.sh <laptop IP>` in
the VDI) or _Bundle_ (API stays private; export, portal storage, import). See
[`todoCollege.md`](todoCollege.md).

**One video without the app:**

```bash
uv run --package nazar-worker nazar-worker local --video PATH --how local --fps 1 --out var/runs/NAME
```

Writes `NAME/artifacts` (all outputs and `report.json`) and `NAME/work` (every model's inputs and
outputs) and prints a per-model summary. Exit 0 only if the job completed, every required model
ran, and (local) every GPU step stayed within budget.

---

## 14. Configuration reference

Template: `.env.example` (never commit real values).

| Variable | Purpose |
| --- | --- |
| `NAZAR_ENV`, `NAZAR_LOG_LEVEL` | environment and logging |
| `NAZAR_API_HOST` / `NAZAR_API_PORT` | API bind (default `127.0.0.1:8000`) |
| `NAZAR_WEB_ORIGINS` | allowed browser origins |
| `NAZAR_STORAGE_DIR` | artifact and upload root (default `var/storage`) |
| `NAZAR_MAX_UPLOAD_MB`, `NAZAR_MAX_VIDEO_SECONDS` | upload limits (2048 MB, 900 s) |
| `NAZAR_SECRET_KEY`, `NAZAR_WORKER_TOKEN` | generated by `env:init` |
| `NAZAR_BOOTSTRAP_ADMIN_EMAIL/PASSWORD` | optional headless operator |
| `NAZAR_DATABASE_URL`, `NAZAR_REDIS_URL`, `NAZAR_S3_*` | optional PostgreSQL, Redis, S3 |
| `NAZAR_FAST3R_PYTHON`, `NAZAR_FAST3R_WEIGHTS`, `NAZAR_FAST3R_MAX_VIEWS` | override model locations |
| `NAZAR_GPU_PYTHON`, `NAZAR_SPLAT_PYTHON`, `NAZAR_GPU_WEIGHTS` | override environments/weights |

---

## 15. Testing and quality assurance

```bash
pnpm check                                  # lint + typecheck + unit tests + contract drift
pnpm test:e2e                               # Playwright: real API + web, desktop and mobile
uv run --package nazar-worker nazar-worker doctor
uv run --package nazar-worker pytest apps/worker/tests
```

- **Python:** API (auth, missions, jobs, sensor pipeline, estimates), contracts, media, worker
  (fusion, forecast, georef, UTM, LAS, GLB, SfM, scaffold). Fusion tests include a synthetic
  scene verifying normals, strict hole fill, no sky invention and moving-pixel exclusion.
- **Web:** Vitest unit tests for the libraries; Playwright end-to-end specs against a real API,
  a real worker (test pipeline, CPU baseline, or Fast3R when `NAZAR_E2E_FAST3R=1`) and a real Vite
  server, with isolated storage per run.
- **Real-browser quality verification (used for the tuning below):** an isolated API + GPU worker
  + Vite server, a Playwright script that signs up, uploads a video, runs Reconstruct, waits for
  completion and screenshots each viewer layer through Chromium with the real GPU (ANGLE/D3D11).
  Software GL (SwiftShader) does **not** render the Spark splat reliably, so splat checks must use
  the real GPU.

---

## 16. Quality-tuning history and lessons

A browser review of the pipeline's output found that **Fast3R's raw cloud looked good but later
stages made it worse.** Each cause was found by measuring, not guessing.

| Symptom (seen in the browser) | Root cause | Fix |
| --- | --- | --- |
| Blue-grey haze burying the scene (131k extra points) | Depth-prior hole fill filled sky and smeared depth edges | Fill only small holes with real Fast3R neighbours, agreeing depth, not sky-coloured (131k → ~10k filled on the Taj test) |
| Hatched stripes on walls/doors | Points on surfaces seen at a grazing angle | Drop points with \|cos(normal, ray)\| < 0.2 |
| Long needles and streaks in the splat | Gaussians could stretch freely; 4,000 iterations, no densification | Needle penalty (axis ratio > 4) |
| Soft, low-detail splat (chairs, window, food lost) | No adaptive densification; 1.3 GB of a 5.5 GB budget used | gsplat densification, SH 2, larger Gaussian cap, 2,500 iterations |
| Densification produced huge blurry blobs (58k Gaussians left) | Scene scale was derived from the camera path (0.41) while the scene radius was ~7; all thresholds 18× off | Scale densification and position learning rate by the cloud's extent; keep camera scale for pose refinement |
| Brown floater above the scene | Large Gaussians far from any data | Post-training prune of large _and_ unsupported Gaussians |
| Black holes at the microwave, window and chair; held-out PSNR fell to 20.5 dB | First floater prune removed _every_ Gaussian far from the cloud, including real ones in areas the cloud missed | Restrict the prune to large _and_ unsupported Gaussians (~0.14 % of the scene) |

**Lessons**

- Judge splats from a novel viewpoint **and** by held-out PSNR; training PSNR alone rewards
  needles (33 dB with needles, 22 dB when over-constrained, 36–38 dB with densification).
- Every threshold that depends on "scene size" must use the scene extent, not the camera path.
- Read the run's own report after every change; the 20.5 dB held-out figure exposed a regression
  that the front-view screenshot alone hid.

---

## 17. Measured results

**Kitchen clip** (`output.mp4`, 640×480, 17 s, 1 fps → 16 frames, local profile, no telemetry).
These runs used the code **before** the height-map surface was merged, so the mesh row is the
Poisson fallback path:

| Stage | Result |
| --- | --- |
| Moving objects | 0 found, nothing masked (≈ 6–9 s, 530–690 MiB) |
| Fast3R | 16 views in 3 passes (≈ 16–27 s, peak ≈ 5.1 GB) |
| Metric3D-v2 ViT-L | depth + normals for 16 views (≈ 45–76 s, peak ≈ 4.7–5.0 GB) |
| Fusion | ≈ 473k points, ≈ 53k from the depth prior, all with prior normals |
| Splat | ≈ 435k Gaussians, 2,500 iterations, SH 2; **held-out PSNR 32.4 dB** (train 37.9 dB), 497 floaters removed; held-out renders reproduce the cabinets, stove, kettle, island, chairs, window and food. Small dark smudges remain at the top right. (Standalone re-run with the final settings; an unpruned 1,500-iteration run reached 36.6 dB, so the floater prune costs a few dB for a cleaner scene.) |
| Mesh (Poisson fallback path) | ≈ 605k vertices, 1.2M triangles, ≈ 2 % inferred (≈ 45–60 s, CPU) |
| Whole job through the browser | **≈ 18 min** (splat ≈ 15 min including setup and evaluation) |

**`sample1.mp4`** (Colosseum orbit, 22–23 frames, earlier profile, 4,000 iterations,
no densification): 8.4–16 min; 549k points; 277k Gaussians; peak GPU 4.6–4.8 GB of 5.5 GB.

All six models ran in every run; peak GPU memory stayed within the budget.

**Verification notes.** (1) The height-map surface + texture path and the automatic frame count
were added by commit `1309307` and were **not** part of these browser runs; the merged branch
was verified by lint and unit tests only, and an indoor clip such as the kitchen has not been
run through the height-map surface (it is designed for aerial passes and falls back to Poisson
when it cannot build one). (2) The last full browser run (≈ 18 min) used the first, broader floater prune and exposed its regression (held-out PSNR 20.5 dB, black holes). The narrowed rule described in §7.6 was then verified by re-training the splat alone on that run's inputs; it has not been re-run end to end through the browser.

---

## 18. Limitations and known issues

- **One-sided relief, not a closed object.** One pass of video shows only what the camera saw.
  The far side is not in the model; the viewer limits the orbit and says so. NAZAR does not
  invent unseen geometry.
- **Detail is bounded by the video.** A 640×480 source cannot yield 4K detail; the splat
  reproduces what the frames contain. More frames add little when camera movement (parallax) is
  small; 4 fps on a short clip yields mostly near-duplicate frames.
- **Scale is relative** unless GNSS telemetry aligns. Metric3D's scale is reported, not applied.
- **Fast3R drift:** on 6 GB, many frames mean many overlapping passes, so small misalignments can
  accumulate; the local frame cap of 64 has not been stress-tested at high fps.
- **The height-map surface assumes an aerial pass** (a surface z = h(x, y)). Overhangs and
  vertical faces become slopes; indoor or all-round scenes depend on the Poisson fallback, which
  has no texture and can leave a minority of its surface inferred.
- **Splat viewer:** the splat smears from steep off-axis angles; software-only browsers may not
  draw it at all.
- **Dark or low-confidence regions** (bright windows, glossy appliances) can come out noisy
  because Fast3R gives them low confidence and the fill rule is deliberately conservative.
- **College profile:** weights (~6.5 GB) are not downloaded here and its forecast is an
  unmeasured estimate.
- **Fast3R licence** is non-commercial/academic; the repository is archived.
- A second full run has not re-timed the corrected time estimate for the new splat schedule.

**Roadmap ideas** (not built): VGGT as an alternative geometry model (fits 6 GB only at ~8–12
frames per pass; original weights are non-commercial), texture baking for the Poisson fallback,
COLMAP as a validator, multi-pass capture guidance, appearance-compensated splat training, SfM-grade pose
refinement before the splat.

---

## 19. Licences

NAZAR's own code is the project's. Third-party components keep their licences: Fast3R (FAIR
Noncommercial Research), YOLO11/Ultralytics (AGPL-3.0), SAM 2 (Apache-2.0), Metric3D (BSD-2),
gsplat (Apache-2.0), Open3D (MIT), Spark (MIT), React/three/R3F (MIT). **Because of Fast3R the
pipeline as configured is for non-commercial/academic use.** Sample videos in `docs/sample/video`
are for testing.

---

## 20. Troubleshooting

| Problem | What to check |
| --- | --- |
| "Project is not running" | `curl http://127.0.0.1:8000/api/ready`: shows database, storage, secrets, operator account, **worker contact** and GPU runtime. The API and web can be up while no worker is attached. |
| Reconstruct does nothing | A worker must be running for the chosen location (`run-local.bat` starts one). `Run on` must match the worker's `--location`. |
| Falls back to "CPU baseline" | The Fast3R runtime is missing: run `pnpm gpu:check` / `pnpm gpu:setup`. The job report shows `fast3r_fallback` and why. |
| Out-of-memory | Close other GPU programs; the runners already shrink passes and retry. Check `report.json` → `resources`. |
| Splat is blank in a headless browser | Software GL cannot draw it reliably; use a GPU-backed browser (headed Chromium with ANGLE/D3D11). |
| Splat looks smeared | Normal off the filmed side; use **Free orbit** knowing the far side was never filmed. |
| Windows run hangs at the end of a GPU step | Fixed: runners leave via `os._exit` after the result event. |
| Port already in use | Another API/web instance is running; stop it or change `NAZAR_API_PORT`/Vite's port. |

---

## 21. Glossary

- **Pointmap:** per-pixel 3D coordinates a model predicts for one image.
- **Fast3R:** a feed-forward multi-view model returning pointmaps, confidence, focal and poses.
- **Metric3D-v2:** monocular metric depth and surface-normal estimator.
- **SAM 2:** promptable segmentation model used to cut moving objects out of frames.
- **Gaussian splat (3DGS):** a scene of many coloured 3D Gaussians rendered by rasterisation.
- **Densification:** adding Gaussians where the image error says detail is missing.
- **SH (spherical harmonics):** the view-dependent colour model; higher degree, more detail.
- **PSNR:** reconstruction quality in dB; **held-out** PSNR scores views not used to fit the scene.
- **Poisson reconstruction:** turns oriented points into a watertight triangle surface.
- **Taubin smoothing:** volume-preserving mesh smoothing.
- **DSM / height map:** a surface described as one height per ground cell.
- **Sim(3):** similarity transform (scale + rotation + translation).
- **GNSS / ENU / UTM:** satellite positions; local east-north-up metres; projected map grid.
- **Parallax:** apparent shift of near vs. far objects as the camera moves; the source of depth.
- **Keyframe:** a frame chosen for quality and viewpoint novelty.
- **Lease:** a worker's time-limited claim on a job.
- **ADR:** architecture decision record (`docs/decisions`).
