# ADR-0003: GPU worker pulls jobs from the API over outbound HTTPS

- **Status:** Accepted; protocol implemented in Milestone 4 (2026-10-27) and exercised locally by the test pipeline. Bundle mode implemented 2026-10-28. Still needs verification on the college VDI (Milestone 1) and a choice between online and bundle mode.

## Context

The SyncVDI/SyncHPC guide (`docs/SyncAI-VDI User Guide.pdf`, read in full including screenshots) documents the following:

- **Portal:** a browser portal at `hpc.cement1882.com` where a user requests a workstation. The request dialog offers Deployment, Application, CPU cores, GPU, RAM, Platform (Windows/Linux) and Duration.
- **Session states:** Requested → Ready → Active → Disconnected. Sessions expire, and duration can be extended.
- **Connection:** "Connect" downloads an **RDP (Windows) or .VNC (Linux)** file.
- **Other modules:** SyncHPC also has Jobs (application-specific job forms), Storage (upload/download files in a user directory), Nodes and Licences.

The guide documents **no** SSH access, inbound ports, REST/GPU API or persistent daemons. So the web/API tier cannot assume it can reach the GPU machine.

## Decision

The GPU worker is a process the user starts inside their VDI session (`nazar-worker run`). It only makes **outbound** HTTP(S) calls to the API:

1. It leases the next queued job with a bearer token (`NAZAR_WORKER_TOKEN`) and gets a lease with an expiry. The lease is renewed by heartbeat.
2. It downloads inputs through authorised artifact routes.
3. It posts stage events and uploads artifacts in chunks. Events are idempotent, keyed by `(job_id, seq)`.
4. If the session expires mid-job, the lease lapses and the job returns to the queue. Completed stages are reused from checkpoints.

Celery remains an option for CPU-side tasks co-located with the API. It is not the GPU transport, because a Celery worker in the VDI would need direct Redis access from the VDI, which is unverified.

## Choosing the GPU per job (2026-11-02)

Each job carries a `compute` target, `local` or `college`, chosen with the **Run on** switch next to Reconstruct (remembered per browser; default local). A worker declares its location (`nazar-worker run --location college`, or `NAZAR_WORKER_LOCATION`) and sends it on every call (`X-Nazar-Worker-Location`); it only leases jobs aimed at that location. So a laptop worker and a college worker can poll the same API without taking each other's jobs, and nothing silently falls back from the college GPU to the laptop. `bundle export` takes college jobs by default; import acts for the location recorded in the bundle. Readiness reports each location's presence and geometry backend (`workers`), which the switch shows.

## Consequences / open questions (Milestone 1)

- **API reachability:** the API must be reachable _from_ the VDI, either by public HTTPS or by the API running inside the same network. This must be verified with a read-only port/HTTP test.
- **Fallback (implemented 2026-10-28, `nazar_worker/bundle.py`):** if no outbound route exists, use bundle mode. Both paths run the same `JobRun` and stage code:
  1. `nazar-worker bundle export --out mission.zip` (next to the API) leases a queued job and saves its inputs. It sends no event, so the lease lapses after 60 s and the job is simply queued again, without using an attempt.
  2. Copy the zip into the VDI (SyncHPC Storage, USB). `nazar-worker bundle run mission.zip --out result.zip` needs no network and no token. A `BundleClient` stands in for the API and records every event and artifact in order.
  3. Copy `result.zip` back. `nazar-worker bundle import result.zip` leases that job by id (new optional `job_id` on the lease request) and replays the recording through the normal worker routes, so the API validates it like a live worker. Artifacts are checksum-verified before anything is sent; a result made from a different video is refused.
  - Neither zip contains the worker token or a live lease id. Stage durations are the real offline ones; event times are the import time, and the job shows an `offline_bundle` info warning saying so.
  - While a bundle is out, the job stays queued: an online worker started meanwhile would take it, and the import is then refused.
- **Persistence:** the only copy of results must never be left in VDI temp storage.
