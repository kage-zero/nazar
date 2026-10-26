# Implementation status

_Last updated: 2026-10-27_

## Current milestone: **Milestone 4 — job/event/worker plumbing done with a synthetic test pipeline**

Real reconstruction (Milestone 3) is **not** built. Everything that streams into the viewer today comes from a fixed synthetic scene and is labelled as such everywhere.

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
| Worker | `doctor`, `stages`, and **`run`**: lease → heartbeat thread → stages → events/artifacts, with cancel, lost-lease and failure handling. Stage adapters skip with a reason. Only the synthetic `test` pipeline has adapters; `standard` fails honestly ("no implementation"). |
| Jobs (Milestone 4) | Contracts: `job.queued`, job/stage snapshot, worker lease/heartbeat/event/artifact models. API: jobs, append-only event log with atomic `seq` and idempotency keys, state machine, lease sweeper, worker routes (bearer token + lease header), artifact declare/upload with size+SHA-256 checks, WebSocket stream with REST catch-up, cancel/retry. Web: live job panel, stage table, outputs with downloads, completion sound/vibration (once per watched job, user toggles), point-cloud and camera-path layers with in-place revision swaps, fit/toggles, frame/units labels, mission kept in the URL. Readiness `worker` check is now real (last contact within 60 s). |
| Docs | Research (sample facts corrected; preflight results), architecture (ingestion flow), environment setup (env:init, operator account), README. |

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

- **Telemetry import** (CSV / DJI SRT) is not built. The API answers "not supported yet", and the UI says so.
- **Under load, E2E timing grows.** Several Chromium instances with software WebGL plus server-side decoding starved the laptop at default parallelism (false timeouts). Local workers are capped at 3; the validation tests have explicit time budgets.
- **Preflight thresholds** were calibrated on the two supplied clips only. Treat them as hypotheses for other footage.
- **Validation runs in the API process** (one background thread). This is fine for one operator. GPU work will use the pull-based worker (ADR-0003).
- **Login throttling is in memory.** It resets on restart and is per process.
- **First-run setup trusts loopback.** Through the Vite dev proxy every request is loopback, so keep the dev server bound to 127.0.0.1 (the default) and use env bootstrap for anything exposed.
- `pytest` shows a harmless `StarletteDeprecationWarning` (the test client wants `httpx2`; not yet vetted).
- Every real reconstruction stage is **not implemented**. The viewer shows geometry only from the labelled synthetic test pipeline.
- The college GPU has not been accessed.

## Next action

0. **Your checks:** [`PENDING_USER_TESTS.md`](PENDING_USER_TESTS.md).
1. **Milestone 1** (needs the user): start a SyncVDI session, run `nazar-worker doctor` and read-only network checks there, record the results, and choose ADR-0003's online or bundle mode.
2. **Milestone 2 remainder:** optional telemetry import (CSV, DJI SRT) attached to a mission, with a time-alignment check against video timestamps.
3. **Milestone 3:** research matrix for the first geometry model (licence, weights, VRAM on 6 GB vs the college GPU), then the first honest point-cloud preview from the selected keyframes.

## Resume instructions

`pnpm install && uv sync --all-packages && pnpm env:init && pnpm check && pnpm test:e2e`, then continue from "Next action". To try it by hand: `pnpm dev`, then `pnpm worker` in a second terminal.
