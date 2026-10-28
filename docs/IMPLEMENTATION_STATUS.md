# Implementation status

_Last updated: 2026-10-28_

## Current milestone: **Milestone 3 (GPU) — Fast3R dense geometry, with the CPU baseline as the visible fallback**

**Reconstruct** now runs **Fast3R** on the GPU when the worker has the Fast3R runtime set up (`pnpm gpu:setup`; this laptop's RTX 4050 is set up). Otherwise it runs the classical CPU structure-from-motion baseline. Either way the result is in a local frame with unknown scale, and the job, every artifact and the viewer say which method ran. If Fast3R fails on a job, the job still completes with the CPU baseline and a visible `fast3r_fallback` warning that gives the reason.

The other GPU models from the brief (Metric3D-v2 scale, InstantSplat, YOLO + SAM2) are **not** integrated. The college GPU (Milestone 1) has not been accessed. The synthetic test pipeline still exists for plumbing checks and stays labelled as synthetic.

**Optional telemetry** (DJI SRT / CSV) can now be attached to a mission. When the camera path matches the GPS track well enough, the result gets a metric scale from GNSS; otherwise it stays local and says why. See the telemetry report below.

Checks that need you (college GPU, sound and vibration, phone, decisions) are listed in [`PENDING_USER_TESTS.md`](PENDING_USER_TESTS.md).

The user had no third-party API keys yet. None are needed so far:

- Machine secrets (`NAZAR_SECRET_KEY`, `NAZAR_WORKER_TOKEN`) are generated locally by `pnpm env:init` into the git-ignored `.env`. The script prints only the variable names.
- The operator account is created in the web app on first run. `NAZAR_BOOTSTRAP_ADMIN_*` became optional, for headless use.
- All API-key placeholders in `.env.example` stay blank.

Milestone 1 (college VDI hardware validation) still needs the user inside a SyncVDI session. It has not started.

## Done

| Area | What exists |
|---|---|
| Monorepo | pnpm 12 + Turborepo 2. uv workspace (Python 3.12). ADR-0001. |
| Contracts | Job state machine, events, artifact manifest, health/readiness (Stage 1). **New:** auth state, credentials, missions, assets (status + progress), preflight report (probe, analysis info, summary, keyframes, warnings, columnar per-frame series). Pydantic → JSON Schema → TS with drift check. |
| Media (`packages/media`, new) | ffprobe parsing (rotation, display size, attached pictures ignored). Packet timestamps; VFR decided from real intervals. Single-pass FFmpeg decode at 320 px gray via argv (no shell). Per-frame sharpness (Laplacian variance), brightness and clipping, change, sub-pixel phase-correlation motion, 48-px viewpoint signature. Flags: blurry, dark, over-exposed, repeated. Keyframe selection by viewpoint novelty with min/max gap, sharpest-in-look-ahead, and a cap of 96. Full-res + thumbnail JPEG extraction, atomic writes, cancellation, `too_long` / `undecodable` / `unreadable` errors. |
| API | First Alembic revision (users, sessions, missions, assets), auto-applied on start. Operator accounts: first-run setup (loopback only, no account yet, never in production) or env bootstrap; scrypt hashes; server-side sessions (SHA-256 of an HttpOnly SameSite=Lax cookie, Secure in production); login throttling; `X-Nazar-Request` CSRF guard on all mutations. Owner-scoped missions. Resumable chunked upload with offset checking (409 returns the server offset), size and extension limits, server-generated storage paths, SHA-256. Background validation/preflight on one thread with live progress, cancel, retry after an internal failure, and re-queue on restart. Routes for the preflight report and keyframe/thumbnail images. Readiness gained an `accounts` check. |
| Web | First-run setup / sign-in, sign-out. Mission create/select. Real upload: chunked XHR with byte progress, cancel, automatic retry with backoff, and resume of an interrupted upload by re-choosing the same file. Validation progress by phase. Rejected/failed states with Remove/Retry. Preflight panel: facts, findings by severity, sharpness-over-time chart (flagged bands, keyframe ticks, hover/keyboard readout), keyframe strip, and a keyframe table. |
| Worker | `doctor`, `stages`, and **`run`**: lease → heartbeat thread → stages → events/artifacts, with cancel, lost-lease and failure handling. Stage adapters skip with a reason. `test` = synthetic plumbing pipeline. **`standard` = CPU SfM baseline** (see the Milestone 3 report). Unusable input fails the job with a plain, non-retryable reason (`StageFailed`). |
| Jobs (Milestone 4) | Contracts: `job.queued`, job/stage snapshot, worker lease/heartbeat/event/artifact models. API: jobs, append-only event log with atomic `seq` and idempotency keys, state machine, lease sweeper, worker routes (bearer token + lease header), artifact declare/upload with size+SHA-256 checks, WebSocket stream with REST catch-up, cancel/retry. Web: live job panel, stage table, outputs with downloads, completion sound/vibration (once per watched job, user toggles), point-cloud and camera-path layers with in-place revision swaps, fit/toggles, frame/units labels, mission kept in the URL. Readiness `worker` check is now real (last contact within 60 s). |
| Docs | Research (sample facts corrected; preflight results), architecture (ingestion flow), environment setup (env:init, operator account), README. |

## Telemetry import and GNSS scale (2026-10-28, Windows 11 laptop, CPU only)

### Implemented

- **Parser and validator** (`packages/media/python/nazar_media/telemetry.py`). It reads text only; nothing is executed or fetched.
  - **DJI SRT**, three layouts:
    - `[latitude: ..] [longitude: ..] [rel_alt: .. abs_alt: ..]` (Mini / Air);
    - Mavic 2's `[latitude : ..] [longtitude : ..] [altitude: ..]`;
    - Phantom's `GPS(lon,lat,alt) BAROMETER:..` (longitude first).
  - **Airdata CSV**: uses `isVideo` to find the video start, and converts feet to metres.
  - **Plain CSV**: `time_s`, `latitude`, `longitude`, plus optional `rel_alt_m` / `alt_m`.
  - **Normalisation:**
    - time becomes seconds from the video start;
    - the altitude keeps its kind: *above take-off*, *datum not stated* or *none*, and is never presented as sea-level height;
    - lat/lon go to east-north-up (ENU) metres through WGS84 ECEF, never treated as metres.
  - **Dropped and counted, never repaired:** samples with no fix (0, 0), out-of-range values, non-increasing times, and jumps faster than 45 m/s.
  - **Gaps** over 1.5 s are listed. Positions are interpolated only *within* a gap-free span.
- **API.**
  - `POST /missions/{id}/assets` with `kind: telemetry`: `.srt`/`.csv`, up to 20 MB, one per mission.
  - The upload goes through the same resumable chunked route as video. It is validated as soon as the last byte arrives: either `ready`, or `rejected` with a plain reason.
  - `GET /assets/{id}/telemetry` returns a `TelemetrySummary`: samples, rate, span, extent, height range, gaps, dropped samples, video coverage (once the video is validated) and plain-language findings.
  - A job pins the mission's accepted telemetry when it is created (migration `0003`). The worker fetches it from `inputs/telemetry`. If it was removed in the meantime, the job records that and stays local.
- **Worker `sensor_optimization` stage** (`apps/worker/src/nazar_worker/georef.py`).
  - A Umeyama Sim(3) fit maps the placed keyframes' camera centres to the GNSS positions at their video times. It searches a ±2 s clock offset in 0.1 s steps, with a small preference for zero, then drops gross outliers once and refits.
  - Two separate claims:
    - **Scale** needs ≥ 5 matched keyframes, ≥ 50 % of placed keyframes matched, a baseline ≥ 20 m, and RMS residual ≤ max(3 m, 5 % of baseline).
    - **Orientation** (an ENU georeference) additionally needs altitude, and a path that is not close to a straight line (planarity ≥ 0.15). Otherwise rotation about the line is undetermined.
  - Results:
    - Scale accepted: final artifacts keep their local coordinates, and their frame says `scale_status: metric_sensor` with `metres_per_unit`.
    - The LAS export is written in metres. It uses ENU axes from the first fix when orientation was also accepted, and local axes otherwise. The system id says which.
    - The report gains a `sensor_alignment` section: every number, the thresholds, the ENU origin, and the reasons any claim was rejected.
    - Rejected: the frame stays `unknown`, and the `scale_unknown` warning says the telemetry was supplied but not applied, and why.
  - GTSAM pose-graph fusion is **not** used. One similarity transform is the honest model for one video with consumer GNSS. The stage label now says "Sim(3) GNSS alignment".
- **Web.**
  - A "Flight telemetry · optional" box in the mission panel: attach, see the summary and findings, remove. Rejected files show their reason.
  - Measure reads "… m (GNSS scale, estimate)" when the frame has a sensor scale.
  - The viewer's Units row shows "1 unit = N m, metric (sensor)".

### Verified

- `pnpm check`: 15 of 15 tasks pass.

  | Package | Result |
  |---|---|
  | media | 30 passed (17 new telemetry tests) |
  | worker | 27 passed (7 new alignment tests) |
  | API | 44 passed, 1 skipped (Fast3R, environment-gated) |
  | web | 33 passed |

- Full E2E: 25 passed, 2 skipped. Attach, summarise, remove and reject telemetry now run on desktop and mobile.
- **Through the real pipeline** (`apps/api/tests/test_sensor_pipeline.py`, CPU baseline on `sample1.mp4`):
  - A synthetic track built from the job's own camera path at 10 m/unit was recovered as **10.024 m/unit** (0.24 %).
  - The pipeline correctly **refused to georeference**: sample1's camera moves along a short, nearly straight arc (planarity < 0.15).
  - The LAS came out in local metres, with an extent 10× the local one.
  - A hovering track (span < 20 m) was reported but not applied, and the frame stayed `unknown`.
- **Unit tests on synthetic tracks:**
  - An orbit with 1.5 m GNSS noise gives scale within 3 % plus a georeference.
  - A 0.8 s clock offset is found within 0.1 s.
  - Straight-line flight gives scale only.
  - Rejected: a hover, telemetry from another flight, telemetry with no altitude, and telemetry with no time overlap.
  - ENU checked against known geodesy: 0.001° of latitude at 41.89° N ≈ 111.07 m, and 0.001° of longitude ≈ 82.9 m.

### Performance-accuracy evidence

- **No real flight log was supplied,** so every accuracy figure above comes from **synthetic** telemetry and is labelled so in the tests. It shows the maths and the acceptance rules work. It says nothing about real DJI GNSS accuracy or SRT clock sync. That needs B11.
- The alignment itself costs well under a second: 41 offsets × one SVD on ≤ 96 keyframes.

### Known limitations

- **Scale quality** is bounded by consumer GNSS (a few metres) and by how far the drone flew. The reported `scale_uncertainty_rel_approx` counts fit noise only, not GNSS bias or the time-sync error that remains after the offset search.
- **The cloud stays in its local frame,** with metres-per-unit metadata. Only the LAS export is converted to metres or ENU. No CRS or GeoKey VLR is written yet, so GIS tools see local ENU metres, not a projected CRS.
- **No altitude** (lat/lon only): no alignment is attempted. A horizontal-only fit would need a known up axis.
- **Formats:** only the SRT layouts and CSV columns above. Other drone logs (e.g. `.DAT`, `.txt` flight records, GPX) are not read.
- **Before validation:** a telemetry file attached before its video is validated shows "coverage known once the video is validated" until then.

### Next step

Run B11 with a real DJI clip and its SRT. Then add a projected CRS (UTM through PyProj, once vetted) to the LAS export when orientation is accepted. After that, GLB export.

## Milestone 3 report — Fast3R GPU geometry (2026-10-27, Windows 11 laptop, RTX 4050 Laptop 6 GB)

### Implemented

- **Isolated GPU runtime** (ADR-0004). Fast3R runs in its own Python 3.11 environment (`var/gpu/fast3r-env`, torch 2.7.1+cu126), never inside the worker. Everything is pinned: source commit `33104d4`, weights revision `a2c770b` with the checkpoint SHA-256, and an exact package freeze (`apps/worker/gpu/requirements-fast3r.txt`). `pnpm gpu:setup` installs it and `pnpm gpu:check` verifies it read-only. No token is needed.
- **Runner** (`apps/worker/gpu/fast3r_runner.py`). It streams JSON events: `loaded`, `plan`, `chunk`, `retry`, `done` and `error`. The details:
  - **Pass size.** It sizes passes from free VRAM. Large sequences go in overlapping passes, aligned by a robust Sim(3) fitted on the shared views. Each pass writes a partial result, so the viewer gets previews while it runs.
  - **Out of memory.** An OOM halves the pass size in-process. A driver-level CUDA error is reported as OOM, so the worker restarts the runner smaller.
  - **Loading.** The checkpoint is read with a streaming reader instead of memory-mapping, because Windows charges a copy-on-write map of the 2.5 GB file against commit. The model is built in fp32 on the GPU, then cast to bf16. Peak host commit is reported.
- **Worker adapter** (`nazar_worker/fast3r.py`, `standard.py`).
  - Runs the runner with a clean environment.
  - Converts pointmaps into NAZAR's frame (levelled, local, unknown scale).
  - Filters by confidence, then labels each point *observed* or *estimated* by a stated heuristic.
  - Publishes preview and final clouds plus the camera path.
  - Falls back to the CPU baseline with a reason.
  - Settings come from `.env` (`NAZAR_FAST3R_*`); relative paths resolve against the env file.
- **Web.** Shared provenance helpers (`lib/provenance.ts`). The job tag reads "GPU · Fast3R" or "CPU baseline", and the viewer label states the method. Help text explains both paths.
- **E2E.** Opt-in Fast3R run: `NAZAR_E2E_FAST3R=1`. E2E ports moved to 18765/15174, so they never collide with other local servers.

### Verified

- Worker: ruff, format and strict mypy clean; 15 tests pass. API: mypy clean; `test_standard_pipeline.py` 4/4 with the GPU configured.
- Those 4 tests cover:
  - the CPU baseline;
  - Fast3R dense on sample1 (all keyframes placed, more than 50k points, cameras above the levelled ground, both confidence labels present);
  - a broken GPU runtime, which falls back visibly;
  - an unconfigured runtime.
- Web: lint, typecheck and Vitest pass, including the provenance tests. Playwright real-data spec passes on the CPU path and, with `NAZAR_E2E_FAST3R=1`, on the Fast3R path (twice).
- The streaming checkpoint reader matches safetensors' own loader on all 712 tensors.
- `scripts/setup_fast3r.py --check --hash` passes against the pinned SHA-256.

### Performance-accuracy evidence

Full table and discussion: `docs/research/model-selection.md` ("Fast3R vs the CPU baseline").

| | sample1 (22 kf) | sample2 (78 kf) |
|---|---|---|
| Fast3R points | 267,786 | 205,362 |
| CPU SfM points | 6,340 | 5,040 |
| Fast3R geometry stage | 13.8 s, of which inference ≈ 4.5 s | 50.5 s, 15 passes |
| Fast3R peak VRAM | 3.1 GiB | 3.9 GiB |
| Alignment self-consistency | 1.6 % residual | 7 % median, 17 % max residual |

There is no ground truth, so these numbers are density, speed and self-consistency, **not** metric accuracy. Run-to-run differences are a median of 0.0003 and a maximum of 0.015 (scene units) from GPU nondeterminism.

### Known limitations

- **Pass chaining on a 6 GB GPU.** On long clips (sample2) the chunk alignment drifts: the camera path shows jumps, and every point is labelled *estimated*. A skeleton-anchored alternative was measured and not adopted (see model-selection). A larger GPU (college VDI) is the expected fix, but that is untested.
- **Windows memory.** Under WDDM the runner needs ≈ 5–8 GiB of free system commit. When the laptop runs short, CUDA fails with "unknown error" and the job falls back to the CPU baseline, visibly.
- **No scale or ground truth.** Metric3D-v2 (scale) and telemetry are not integrated.
- **Not interactive yet.** Confidence colouring in the viewer, measurement tools, exports (LAS/GLB) and meshing are not built.
- **Licence.** Fast3R is non-commercial and archived upstream. It is approved for this academic project only.

### Added after the report (same day)

- **Confidence colouring in the viewer.** Final PLY clouds carry a per-point `confidence` class (1 observed, 2 estimated). **Colour by confidence** recolours the cloud (blue/orange; the palette is validated for colour-vision deficiency on the black viewer) and shows a counted legend. API tests check that the classes match the report; E2E checks the legend on both the CPU and Fast3R paths.
- **LAS export.** The final cloud is also published as LAS 1.2, point format 2 (`nazar_worker/las.py`, numpy only):
  - no CRS, because the frame is local; the system identifier says "NAZAR local frame, no CRS";
  - axes converted to +Z up;
  - confidence class in the user-data byte.

  Tests check the header byte offsets against the specification and a round trip, and that the real pipeline's LAS equals its PLY. Opening it in a third-party viewer is pending (B9).
- **Relative measurement.** **Measure** lets you click two cloud points; the viewer draws the segment and reports the distance as "N units (relative; scale unknown)", never in metres, while the scale is unknown. E2E picks two points on both the CPU and Fast3R clouds.
- **Readiness `gpu` check is real.** Workers report their geometry backend (`fast3r` or `cpu-baseline`) on each lease. Readiness shows OK for Fast3R, or explains that the CPU baseline is in use.

### Next step

1. Your checks: B7, B8 and B9 in `PENDING_USER_TESTS.md`.
2. Milestone 1 on the college GPU: `pnpm gpu:check` there, then sample2 with larger passes.
3. On the laptop: telemetry import (gives scale and position), and a GLB export.

## Milestone 3 report — CPU baseline slice (2026-10-27, Windows 11 laptop, CPU only)

### Implemented

- `sfm.py`, a classical incremental SfM:
  - SIFT features, windowed mutual matching, essential-matrix RANSAC, union-find tracks;
  - an initial pair chosen for parallax (planar and rotation-only pairs are rejected);
  - EPnP registration and parallax-gated triangulation;
  - sparse bundle adjustment with an analytic Jacobian, Huber loss and a shared estimated focal length;
  - pruning, normalisation and up-alignment by a RANSAC plane fit.
  - It yields a preview snapshot after initialisation and after every 4 registrations, and stops at safe points when a job is cancelled.
- `baseline.py`, the standard pipeline:
  - keyframes are fetched from the API;
  - `preview-{n}` point clouds stream while geometry runs;
  - the final cloud is a statistically filtered one, published with the camera path (poses + estimated focal length);
  - each point is labelled observed or estimated;
  - a processing report (`nazar.processing-report/1`) records the method, statistics, confidence rule, coordinate frame, timings, resources, skip reasons and limitations.
  - Depth priors, dynamics and surface are skipped with reasons; sensor fusion is skipped when there is no telemetry.
- Web:
  - **Reconstruct** is enabled and starts the standard pipeline.
  - The job tag reads "CPU baseline". The viewer tag comes from artifact provenance ("CPU baseline · sparse SfM").
  - Stage copy no longer promises outputs this run cannot make (no GLB/LAS/Gaussian claims).
- Dependencies (worker only): `opencv-python-headless` 5.0 (Apache-2.0), `scipy` 1.18 (BSD-3), plus `scipy-stubs` for dev. No model weights.
- `docs/research/model-selection.md`: licence and hardware matrix for Fast3R, VGGT, MASt3R and COLMAP, verified on the official repositories. Nothing was downloaded.

### Verified

- Worker pytest, 14 tests:
  - bundle adjustment recovers a perturbed synthetic scene and an 8 % focal error back to the injected 0.3 px noise;
  - triangulation refuses zero-parallax pairs;
  - up-alignment levels a tilted ground plane;
  - the array PLY writer is byte-identical to the tuple writer;
  - **real `sample1.mp4` → real preflight → reconstruction**: previews grow monotonically, ≥ 80 % of keyframes are registered, ≥ 3000 points, mean reprojection < 1.5 px, and the cameras sit above the ground.
- The analytic BA Jacobian matches finite differences to 1e-8.
- API test: a standard job on undecodable keyframes fails with "Keyframe 1 could not be decoded.", is not retryable, and publishes no artifacts.
- Playwright **real-data E2E** (desktop):
  - upload sample1, press Reconstruct, and a real preview cloud (> 500 points) renders *while the job is still running*;
  - the job completes and the final cloud has > 3000 points;
  - geometry shows done and depth priors show skipped;
  - the unknown-scale warning is shown;
  - the downloaded report has ≥ 18 registered keyframes, mean reprojection < 1.5 px, `scale_status: unknown`, and a point count equal to the cloud on screen;
  - no console errors.
- E2E now runs two real worker processes (test and standard), as in deployment.
- **Bug found and fixed by the fuller E2E:** a Cancel that landed between the worker's cancel check and its next `stage.started` made the job end *failed* instead of *cancelled*. The worker now asks the API when a stage start is refused, and reports a cancellation when that is the reason. A deterministic API regression test injects the cancel at exactly that point; it fails without the fix.
- Totals: `pnpm check` 15/15 (API 35, worker 14, media 13, contracts 7, web 24). Playwright 23 passed, 2 skipped (desktop-only by design).
- The final screenshot was reviewed: the Colosseum's oval ring is visible.

### Performance-accuracy evidence

sample1 (22 keyframes, 640×360):

| Measure | Result |
|---|---|
| Registered keyframes | 22 / 22 |
| Points (raw / after outlier filter) | 6454 / 6340 |
| Observed / estimated points | 4518 / 1822 |
| Mean reprojection | 0.63 px |
| BA RMS (Huber) | 1.06 px |
| Estimated focal length | ≈ 481 px |
| Standalone timing | first preview ≈ 8–13 s, total ≈ 18 s |
| Timing inside the busy E2E run (browser + API + 2 workers on the same laptop) | first preview 18.5 s, geometry 34.3 s |

There is no ground truth for the sample, so absolute accuracy is **not measured**. The reprojection error measures internal consistency only.

### Known limitations

- Sparse points only. There is no dense surface, mesh or Gaussian scene; textureless areas are empty.
- Unknown scale and a local frame. Up is estimated from the dominant plane.
- The focal length is not calibrated, and no lens distortion is modelled.
- Footage that only rotates or hovers has no parallax: the job fails with a reason instead of inventing geometry.
- sample2 (78 keyframes) has not yet been run end to end through the UI (B7).
- The GPU models from the brief are not integrated (C1 licence approval + Milestone 1 GPU access).

### Next step

1. Get C1 and C3 answers, and access to the college GPU.
2. Write a Fast3R adapter for the `geometry` stage behind the same contract. The CPU baseline stays as the fallback.
3. Meanwhile, on CPU: telemetry import, measurement tools and confidence colouring in the viewer.

## Milestone 4 report (2026-10-27, Windows 11 laptop, CPU only)

### Implemented

- Job lifecycle (`created → queued → stages → completed | failed | cancelled`), derived only from the append-only event log.
- Pull-based worker protocol from ADR-0003: lease, heartbeat, events, inputs, artifacts, lease expiry and re-queue.
- Live browser updates over WebSocket, with REST catch-up and backoff reconnect.
- Progressive viewer: preview revisions, then the final cloud and camera path, without resetting the camera.
- Completion feedback, outputs inventory, cancel and retry.
- `pnpm worker` (test pipeline) and real `worker` readiness.

### Verified

- `pnpm check`: 15/15 Turbo tasks pass. That covers pytest (contracts 7, worker 8, media 13, API 34), vitest 24, ruff, strict mypy, ESLint, Prettier, `tsc` and contract drift.
- API tests cover:
  - a full run through the real `run_loop`;
  - WebSocket replay from a cursor, plus origin and anonymous rejection;
  - token checks, event idempotency and state-machine rejections;
  - an artifact checksum mismatch;
  - lost lease → re-queue;
  - cancel and retry;
  - the `standard` pipeline failing as non-retryable;
  - owner isolation.
- Playwright: 22 passed and 1 skipped (desktop-only by design), on desktop and Pixel 7. The suite runs the real API, a real worker process (with a random per-run token that is never written to disk) and Vite. The job tests check:
  - stages stream;
  - a preview cloud is rendered **before** the job completes;
  - completion shows the final cloud;
  - the sensor stage is skipped with "No telemetry";
  - the synthetic warning is shown;
  - the downloaded PLY is valid;
  - layer toggles and Fit work;
  - a reload during a running job resumes it, then cancel and retry work.
- Screenshots of the completed job were reviewed at desktop and mobile widths.

### Performance-accuracy evidence

- **Accuracy:** none. The geometry is synthetic, so no accuracy claim is made.
- **Plumbing timings** (test pipeline, `--step-delay 0.8`):
  - the run takes about 10 s;
  - preview revisions have about 13k points;
  - the final cloud has about 26k points (≈380 KB binary PLY);
  - an event reaches the browser within about 0.25 s, which is the server poll interval.

### Known limitations

- No real reconstruction yet (Milestone 3).
- The WebSocket polls the database every 0.25 s; there is no pub/sub, which is fine for one operator.
- Leases live in SQLite. With more than one API process you would need PostgreSQL and row locks.
- Artifacts are stored on the API host's disk. The worker reads inputs over HTTP; there is no shared storage.
- Completion sound and vibration, network-drop reconnect and VDI connectivity have not been checked by a person (see `PENDING_USER_TESTS.md`).
- The GPU readiness check still says "not built yet".

### Next step

Milestone 3 research matrix: candidate geometry models with licence, weight terms and VRAM needs. Nothing gets downloaded until you approve it (C1 in `PENDING_USER_TESTS.md`).

## Milestone 2 evidence (actually run, 2026-10-26, Windows 11 laptop, CPU only)

1. **`pnpm check`:** 15/15 Turbo tasks pass.
   - pytest: contracts 6, worker 5, media 13, API 23.
   - vitest: 16, including the upload resume/retry state machine and chart downsampling.
   - ruff, strict mypy, ESLint, Prettier, `tsc`, contract drift.
2. **API tests cover:**
   - setup closes after the first account and is refused in production;
   - bootstrap login, wrong password, throttling (429), CSRF header (403), short password (422);
   - missions require sign-in;
   - wrong type / oversize rejected; stale and over-long chunks;
   - a corrupt `.mp4` is rejected with a reason and can be replaced;
   - **`sample1.mp4` upload → `ready` → preflight with >500 frames and ≥8 keyframes → JPEG thumbnail served;**
   - cancel during validation cleans up.
3. **Playwright:** 18 passed, 1 skipped (keyboard test is desktop-only by design), desktop and Pixel 7, real API + Vite.
   - A `setup` project creates the operator through the first-run UI in a fresh per-run database.
   - Sample upload through the UI → preflight panel, chart, ≥8 loaded keyframe thumbnails, no console errors.
   - Non-video rejected in the browser; corrupt video rejected by the server and removable.
   - Sign in (wrong then right password) and sign out.
   - Screenshots of the preflight screen were reviewed at both sizes. The chart now draws at real pixel width so its labels stay 10 px.
4. **Preflight numbers** (see `docs/research/README.md`): sample1 22 keyframes in ≈1.6 s; sample2 78 keyframes in ≈3 s with a real repeated-frames warning (289 of 1033).
5. **Secrets:** `.env` stays ignored. `playwright/.auth/` (E2E session cookie) is ignored. No secret values appear in code, tests, logs or this file.

## Known gaps and warnings

- **Telemetry** is tested on synthetic tracks and on synthetic telemetry through the real pipeline only. No real flight log has been tried yet (B11).
- **Under load, E2E timing grows.** Several Chromium instances with software WebGL plus server-side decoding starved the laptop at default parallelism (false timeouts). Local workers are capped at 3; the validation tests have explicit time budgets.
- **Preflight thresholds** were calibrated on the two supplied clips only. Treat them as hypotheses for other footage.
- **Validation runs in the API process** (one background thread). This is fine for one operator. GPU work will use the pull-based worker (ADR-0003).
- **Login throttling is in memory.** It resets on restart and is per process.
- **First-run setup trusts loopback.** Through the Vite dev proxy every request is loopback, so keep the dev server bound to 127.0.0.1 (the default) and use env bootstrap for anything exposed.
- `pytest` shows a harmless `StarletteDeprecationWarning` (the test client wants `httpx2`; not yet vetted).
- Real reconstruction is **Fast3R** (GPU, dense) or the **CPU SfM baseline** (sparse). Metric3D-v2, InstantSplat and YOLO + SAM2 are not implemented.
- The college GPU has not been accessed.

## Next action

0. **Your checks:** [`PENDING_USER_TESTS.md`](PENDING_USER_TESTS.md).
1. **Milestone 1** (needs the user): start a SyncVDI session, run `nazar-worker doctor` and read-only network checks there, record the results, and choose ADR-0003's online or bundle mode.
2. **Milestone 3 (GPU), continued:** run Fast3R on the college GPU, where long clips should need fewer passes, and compare it with the laptop numbers in `docs/research/model-selection.md`.
3. **Telemetry with real data** (B11), then a projected CRS for georeferenced LAS, then GLB export.

## Resume instructions

`pnpm install && uv sync --all-packages && pnpm env:init && pnpm check && pnpm test:e2e` (optionally `pnpm gpu:check`), then continue from "Next action". To try it by hand: `pnpm dev`, then `pnpm worker` in a second terminal.
