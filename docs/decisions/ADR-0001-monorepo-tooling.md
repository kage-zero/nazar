# ADR-0001: Turborepo + pnpm for TypeScript, uv workspace for Python

- **Status:** Accepted (2026-10-26)
- **Context:** The brief requires a Turborepo monorepo, a TypeScript web layer and Python/FastAPI. The workspace was empty apart from `docs/`, so no existing conventions applied.

## Decision

- **JS/TS:** pnpm 12 workspaces (`apps/*`, `packages/*`) orchestrated by Turborepo 2. Exact versions are pinned in `package.json`, and `pnpm-lock.yaml` is committed. pnpm's supply-chain release-age policy stays enabled; on 2026-10-26 we pinned `typescript-eslint@8.71.2` instead of adding an exclusion for the day-old 8.72.1.
- **Python:** a uv workspace rooted at `pyproject.toml` with members `apps/api`, `apps/worker` and `packages/contracts`. `uv.lock` is committed and Python is pinned to 3.12 (`.python-version`).
- **Bridge:** each Python app has a thin `package.json` whose scripts call `uv run …`, so `turbo run lint typecheck test` covers both stacks. Long-running `dev` tasks set `cache: false` and `persistent: true`.
- **TypeScript 6.0.3**, not 7.x. typescript-eslint 8.x supports TS `<6.1`.
- **ESLint 9.39** (flat config). ESLint 10 exists, and pnpm prints a deprecation notice for 9.x. We'll revisit once `eslint-plugin-react-hooks` and typescript-eslint document ESLint 10 support.

## Not created (yet)

`packages/ui` and `packages/config`. There is one web app, so the design primitives live in `apps/web/src/components/ui.tsx`, and the shared TS config is the root `tsconfig.base.json`. Extract them when a second consumer exists.

## Consequences

Contributors need Node ≥ 22, pnpm 12, and uv (which downloads Python 3.12 itself). The Python stacks install without any JS tooling and vice versa.
