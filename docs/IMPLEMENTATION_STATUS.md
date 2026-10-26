# Implementation status

_Last updated: 2026-10-26_

## Current milestone: **Gate 1 — scaffold complete, WAITING for the user**

The user fills the blank values in their local, git-ignored `.env`, then replies `continue`. Do not start pipeline work before that.

## Done (Stage 1)

| Area | What exists |
|---|---|
| Monorepo | pnpm 12 + Turborepo 2. uv workspace (Python 3.12). Lockfiles: `pnpm-lock.yaml`, `uv.lock`. ADR-0001. |
| Contracts | `packages/contracts`: Pydantic models (job state machine, 12 typed job events, artifact manifest, health/readiness) → JSON Schema → generated TS, with a drift check. |
| API | `apps/api`: FastAPI `GET /api/health` (liveness) and `GET /api/ready` (DB, storage, required config, worker/GPU as `not_implemented`). Typed settings with `SecretStr`, blank ⇒ unset, structured JSON logs, CORS. SQLAlchemy engine, Alembic configured (no revisions yet). |
| Worker | `apps/worker`: `nazar-worker doctor` (read-only GPU/disk/toolchain), `stages` (honest plan), `run` (exits 2: not implemented). `StageAdapter` boundary. |
| Web | `apps/web`: design-system shell per `docs/DESIGN.md`, live API status badge + readiness panel, mission empty state, video-picker shell (client pre-check only; upload disabled and labelled), R3F viewport scaffold (grid, axes, orbit, reset, layer toggles; no geometry), pipeline overview labelled as not running. |
| Infra | Optional `infra/docker-compose.yml` (PostGIS, Redis, MinIO) with credentials from `.env`. |
| Docs | ADR-0001…0005, architecture overview, testing, research notes, environment setup, README. |

## Gate 1 evidence (actually run, 2026-10-26, Windows 11 laptop)

1. **Layout and lockfiles:** both lockfiles created. Supplied `docs/` files untouched (top-level `docs/*.md` and PDF are excluded from Prettier).
2. **JS install:** `pnpm install` OK. The lockfile passes pnpm's supply-chain release-age policy (typescript-eslint pinned to 8.71.2).
3. **Web:**
   - `pnpm dev` serves `http://127.0.0.1:5173` (HTTP 200).
   - Playwright renders it in Chromium at desktop and Pixel 7 sizes.
   - Screenshots were compared with DESIGN.md; the viewer was made taller on mobile after review.
4. **API:**
   - `/api/health` returns `ok` directly and through the Vite proxy.
   - `/api/ready` returns `ready=false`, with the four required secrets `not_configured`, DB and storage `ok`, worker and GPU `not_implemented`.
5. **`pnpm check`:** 12/12 Turbo tasks pass.
   - ESLint (strict type-checked) and Prettier
   - `tsc`: web + contracts
   - ruff + ruff format, strict mypy (api, worker, contracts)
   - pytest: 17 tests (contracts 6, api 6, worker 5)
   - vitest: 7 tests
   - contract drift check
6. **Playwright:** 11 passed, 1 skipped (the keyboard test is desktop-only by design). The suite covers:
   - main screen with no console errors
   - offline indicator
   - picker accepts `docs/sample/video/sample1.mp4` and rejects `.txt`
   - upload button disabled
   - viewer toggles and reset
   - skip link and focus
   - no horizontal overflow on desktop and mobile

   **Flake note:** the very first run had 4 failures that we could not reproduce in 8 later runs (incl. 4 cold-cache runs and `--repeat-each=4`). The errors were not captured, because the report was overwritten. Mitigations: Vite pre-bundles three/R3F/drei (`optimizeDeps.include`), and the expect timeout is now 10s for software WebGL. Watch for recurrence.
7. **Secrets:**
   - `.env.example` and `.env` have blank secret values.
   - `.env` is git-ignored (verified with `git check-ignore`).
   - The initial commit was scanned for secret patterns.
   - Tests assert that `/api/ready` and the settings repr never echo secret values.
8. **This file:** written.

## Known gaps and warnings

- `pytest` shows a `StarletteDeprecationWarning` (Starlette's test client wants `httpx2`). It is harmless. We haven't added `httpx2` yet; vet the package before adopting it.
- pnpm prints a deprecation notice for ESLint 9.39 (ADR-0001).
- On Windows, stopping `pnpm dev` from a non-interactive runner can orphan the uvicorn/vite children. Ctrl+C in a terminal is fine.
- Accounts/auth, uploads, jobs, events and artifacts are **not implemented**.
- College GPU not yet accessed. All hardware facts so far are from the dev laptop (RTX 4050 Laptop, 6 GB).

## Next action (after `continue`)

1. Re-read this file, `docs/ENVIRONMENT_SETUP.md`, `git status`. Run `/api/ready` and confirm the four required secrets report present (values never printed).
2. **Milestone 1 (environment and hardware validation):**
   - The user starts a SyncVDI session (prefer Linux).
   - In it, run `nazar-worker doctor` and read-only network checks: outbound HTTPS to the API host, pip/uv/Hugging Face reachability, disk quota, session length.
   - Record the results in `docs/research/` and pick ADR-0003's online or bundle fallback.
3. **Milestone 2 (contracts and ingestion), which can proceed in parallel on the laptop:**
   - First Alembic revision: users, missions, assets, jobs, job_events, artifacts.
   - Bootstrap admin + session auth.
   - Chunked video upload with server-side ffprobe/decoder validation.
   - Telemetry upload slot.
   - Preflight quality scoring + keyframe selection on `sample1.mp4`/`sample2.mp4` (sample2 is VFR: use timestamps).
4. Milestone 3: Fast3R vs alternatives research matrix (licence/weights/VRAM on 6 GB and the college GPU) → first honest point-cloud preview in R3F.

## Resume instructions

`pnpm install && uv sync --all-packages && pnpm check && pnpm test:e2e`, then continue from "Next action".
