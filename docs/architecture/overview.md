# Architecture overview

```text
 Browser (React + R3F)                    API tier                         GPU tier (college VDI / laptop)
 ─────────────────────                    ────────                         ───────────────────────────────
 apps/web  ── REST /api/* ──────────────▶ apps/api (FastAPI)   ◀── HTTPS ── apps/worker  (nazar-worker run)
           ◀─ WebSocket job events ──────  │  SQLite | PostgreSQL/PostGIS     │ pulls jobs, posts events,
           ◀─ artifact bytes (authorised)  │  local FS | MinIO (S3)           │ uploads artifacts
                                           │  in-process | Redis fan-out      ▼
                                           ▼                                 per-model pinned envs (ADR-0004)
                                     packages/contracts  (Pydantic → JSON Schema → TypeScript)
```

## Component boundaries

| Component            | Owns                                                                            | Never does                                                |
| -------------------- | ------------------------------------------------------------------------------- | --------------------------------------------------------- |
| `apps/web`           | UI state, rendering, client pre-checks                                          | Trust its own checks; hold large geometry in global state |
| `apps/api`           | Auth, missions, uploads, job state machine, event log, artifact metadata/URLs   | Run GPU inference in a request handler                    |
| `apps/worker`        | Leasing jobs, stage orchestration, checksums, atomic writes                     | Touch the DB directly; import torch in the orchestrator   |
| `packages/media`     | Probing/decoding video via FFmpeg argv calls, frame metrics, keyframe selection | Know about HTTP, the DB or users                          |
| `packages/contracts` | Event/artifact/health/job-status schemas, transition table                      | Contain business logic beyond the state machine           |

## Contracts (`packages/contracts`)

- **Source of truth:** Pydantic models in `python/nazar_contracts`.
- **Generation:** `pnpm contracts:generate` exports `schema/contracts.schema.json` plus `schema/constants.json` (stage order, transitions), then generates `src/generated.ts`.
- **Drift guard:** `pnpm contracts:check` fails when the committed schema or TS is out of date.

### Job state machine

`created → validating → queued → preprocessing → geometry → depth_priors → dynamic_analysis → sensor_optimization → dense_reconstruction → surface_processing → analysis → exporting → completed`

- **Skips:** a stage may jump forward over later-listed optional stages. Each skipped stage is reported with `stage.skipped` and a reason. A skip is never reported as `stage.completed`.
- **Failure and cancellation:** every non-terminal state can go to `failed` or `cancel_requested`. `cancel_requested` goes to `cancelled` (or `failed`).
- **Retry:** `failed` or `cancelled` can go back to `queued`.
- **Completion:** `completed` is reachable **only** from `exporting`.

### Event envelope

Each event carries `schema_version`, `job_id`, `seq` (per-job cursor, ≥ 1), `ts`, `status`, `stage`, `type` and typed `data`. The types are:

`job.created`, `stage.started`, `stage.progress`, `stage.completed`, `stage.skipped`, `warning`, `artifact.available`, `preview.updated`, `job.completed`, `job.failed`, `cancel.requested`, `job.cancelled`.

`stage.progress` carries `completed`/`total`/`unit` only when real work is countable. Otherwise both are null, meaning indeterminate progress.

### Artifact manifest

A manifest records:

- `kind` and a monotonic `revision`
- `media_type`, `byte_size` and `checksum_sha256`
- `frame`: type, units, `scale_status`, CRS and vertical datum, axes
- `transform_to_frame`, `bounds`, `point_count`, `lod`
- `source_frames`
- `provenance`, including the `test_pipeline` flag

It contains no paths or storage credentials.

## Ingestion (Milestone 2)

1. **Auth.** One operator account, from first-run setup (loopback only) or env bootstrap. Passwords are hashed with scrypt. Sessions are server-side, keyed by the SHA-256 of an HttpOnly cookie. Every state-changing `/api` request must carry `X-Nazar-Request: 1`; this is the CSRF guard, and CORS allows that header only from configured origins. Failed logins are throttled per client and email.
2. **Missions** are owned by the operator. Another owner's ids return 404.
3. **Upload.** `POST /api/missions/{id}/assets` registers `{kind, filename, byte_size}`, checking extension and size. Bytes go to `PUT /api/assets/{id}/content?offset=N` in chunks. A wrong offset returns 409 with the server's offset, so retries and resumes are safe. Files are stored under server-generated ids only.
4. **Validation.** On the last chunk the API hashes the file (SHA-256), marks it `validating` and queues it on a single background thread: ffprobe → full decode at 320 px → per-frame sharpness, exposure, change, motion and viewpoint signature → keyframe selection → full-resolution and thumbnail JPEGs → `preflight.json` (atomic writes). Progress is written to the asset row, which the web app polls. Cancel is `DELETE`: the job stops at its next checkpoint and removes its files. Assets left `validating` by a restart are re-queued on startup. Undecodable files end `rejected` with a user-safe reason.
5. This in-process executor is CPU-only. GPU stages will run in the pull-based worker (ADR-0003).

## Coordinate-frame rules (summary; details arrive with Milestone 3)

- Video-only output is `local_reconstruction`, with `scale_status` `unknown` or `relative`. Nothing is called metric or georeferenced without evidence.
- The stored axis convention is right-handed, +Y up, −Z forward (OpenGL / three.js). Every adapter converts its model's native convention, with a unit test per adapter.
- Lat/lon are never treated as Cartesian metres. ENU/ECEF/UTM conversions go through PyProj with the CRS and vertical datum recorded.

## Progressive streaming plan (Milestones 3–4)

1. The first `artifact.available(point_cloud_preview, revision=1)` is emitted as soon as the geometry stage writes valid points.
2. The browser fetches binary chunks (not JSON points) via authorised URLs and swaps buffers in place without resetting the camera.
3. A higher `revision` supersedes older ones, and stale chunks are dropped.
4. The completion effect fires once, keyed by job id, on `job.completed` only.
