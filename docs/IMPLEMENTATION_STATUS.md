# Implementation status

_Last updated: 2026-10-26_

## Current milestone: **Milestone 2 — ingestion slice done (telemetry import still open)**

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
| Worker | Unchanged since Stage 1: `doctor`, `stages`; `run` exits 2 (not implemented). |
| Docs | Research (sample facts corrected; preflight results), architecture (ingestion flow), environment setup (env:init, operator account), README. |

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
- Jobs, events, artifacts and every reconstruction stage are **not implemented**. The viewer shows no geometry.
- The college GPU has not been accessed.

## Next action

1. **Milestone 1** (needs the user): start a SyncVDI session, run `nazar-worker doctor` and read-only network checks there, record the results, and choose ADR-0003's online or bundle mode.
2. **Milestone 2 remainder:** optional telemetry import (CSV, DJI SRT) attached to a mission, with a time-alignment check against video timestamps.
3. **Milestone 3:** research matrix for the first geometry model (licence, weights, VRAM on 6 GB vs the college GPU), then the first honest point-cloud preview from the selected keyframes.

## Resume instructions

`pnpm install && uv sync --all-packages && pnpm env:init && pnpm check && pnpm test:e2e`, then continue from "Next action".
