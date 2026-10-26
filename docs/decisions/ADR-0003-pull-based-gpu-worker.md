# ADR-0003: GPU worker pulls jobs from the API over outbound HTTPS

- **Status:** Accepted for implementation in Milestone 4 (2026-10-26). Needs verification on the college VDI in Milestone 1.

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

## Consequences / open questions (Milestone 1)

- **API reachability:** the API must be reachable _from_ the VDI, either by public HTTPS or by the API running inside the same network. This must be verified with a read-only port/HTTP test.
- **Fallback:** if no outbound route exists, use a manual protocol. The user runs the worker on a mission bundle copied into the VDI, then uploads the result bundle via SyncHPC Storage or another approved channel. The bundle format will equal the artifact contract, so both paths share code.
- **Persistence:** the only copy of results must never be left in VDI temp storage.
