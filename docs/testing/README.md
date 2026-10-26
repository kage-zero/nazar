# Testing

| Command (repo root)                                    | What it runs                                                                                        | Needs                                                                  |
| ------------------------------------------------------ | --------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `pnpm check`                                           | Turbo: ESLint+Prettier, `tsc`, ruff, ruff-format, strict mypy, pytest, vitest, contract drift check | Node, pnpm, uv                                                         |
| `pnpm test`                                            | pytest (contracts, api, worker) + vitest (web)                                                      | —                                                                      |
| `pnpm test:e2e`                                        | Playwright against the real FastAPI + Vite dev servers (desktop 1440×900 and Pixel 7)               | Chromium (`pnpm --filter @nazar/web exec playwright install chromium`) |
| `pnpm --filter @nazar/web exec playwright show-report` | Open the last HTML report (traces, videos and screenshots on failure)                               | —                                                                      |

## E2E profile

`apps/web/playwright.config.ts` starts:

- the API on port **8765** with `NAZAR_ENV=test`, isolated storage `var/e2e-storage`, and every secret forced blank, so readiness is deterministic whatever your local `.env` holds;
- Vite on port **5174**, proxied to that API.

It does not touch your dev servers on 8000/5173.

Network mocking is used only to simulate an unreachable API (the offline indicator test). Every other assertion uses the real backend.

## Profiles still to add

- `test:e2e:gpu`: real neural pipeline on `docs/sample/video/sample1.mp4` (and `sample2.mp4`). It records hardware, VRAM, runtime and time to first preview. It is never part of the fast suite.
- Deterministic test pipeline (`NAZAR_PIPELINE_MODE=test`): emits small real-format PLY/JSON fixtures through the same API/event contracts, labelled `test_pipeline: true` in provenance.

## Gate 1 evidence (2026-10-26)

See `docs/IMPLEMENTATION_STATUS.md`.
