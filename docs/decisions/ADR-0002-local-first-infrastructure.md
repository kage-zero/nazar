# ADR-0002: Local-first defaults; PostgreSQL/PostGIS, Redis, MinIO optional

- **Status:** Accepted (2026-10-26)

## Context

Observed on the development laptop (2026-10-26):

- Docker is not installed.
- There is no running PostgreSQL. `C:\Program Files\PostgreSQL\17` and `\18` hold only leftovers and no `bin/`.
- There is no Redis.

The brief prefers PostgreSQL/PostGIS + Redis + MinIO. The college VDI cannot be assumed to have Docker either.

## Decision

- `NAZAR_DATABASE_URL` blank ⇒ SQLite at `<NAZAR_STORAGE_DIR>/nazar.db`. Set it to use PostgreSQL/PostGIS. The models will use SQLAlchemy types portable to both, and spatial columns will target PostGIS. Spatial features will be gated on a PostgreSQL URL.
- `NAZAR_S3_*` blank ⇒ local filesystem storage under `var/storage` (git-ignored). The S3/MinIO adapter will share the same interface. Readiness reports it as `not_implemented` until it exists.
- `NAZAR_REDIS_URL` blank ⇒ in-process event fan-out (single API process). Redis is needed only for multiple API instances.
- `infra/docker-compose.yml` provides PostGIS 17, Redis and MinIO for anyone who has Docker. All of its credentials come from `.env`.
- Alembic is configured (`apps/api/migrations`). The first revision lands with the first real tables in Milestone 2, so there is no empty placeholder migration.

## Consequences

`pnpm dev` works on a bare laptop. Durable job/event records still go in a real database (SQLite file locally), never in Redis alone. SQLite allows a single writer, which is fine for one API process and one GPU worker.
