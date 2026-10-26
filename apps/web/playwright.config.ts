import { defineConfig, devices } from '@playwright/test';
import { randomBytes } from 'node:crypto';
import { OPERATOR_STATE } from './e2e/operator';

const REPO_ROOT = '../..';
// Uncommon ports, overridable, so the suite never talks to something else already listening
// (a health check answered by another local app would start the tests against the wrong server).
const API_PORT = Number(process.env.NAZAR_E2E_API_PORT ?? 18765);
const WEB_PORT = Number(process.env.NAZAR_E2E_WEB_PORT ?? 15174);
// One storage dir per run so first-run setup always starts from an empty database.
// Set here, in the main process, so every worker inherits the same value.
process.env.NAZAR_E2E_RUN ??= String(Date.now());
// Random per run, shared only by the E2E API and the E2E worker. Never written to disk.
const WORKER_TOKEN = (process.env.NAZAR_E2E_WORKER_TOKEN ??= randomBytes(24).toString('hex'));

/**
 * Fast deterministic E2E profile: real FastAPI + real worker (test pipeline) + real Vite dev
 * server. No GPU, no weights.
 * The API runs with an isolated storage dir and secrets forced blank so readiness is
 * deterministic regardless of what the developer has put in their local .env.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  // Each worker runs Chromium with software WebGL next to the API's CPU-bound video
  // validation; more than a few workers starves the machine and causes false timeouts.
  workers: process.env.CI ? 2 : 3,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  // WebGL runs in software (SwiftShader) in headless Chromium; first compile can be slow.
  expect: { timeout: 10_000 },
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    // Creates the operator through the real first-run UI and saves the session cookie.
    { name: 'setup', testMatch: /operator\.setup\.ts/, use: { ...devices['Desktop Chrome'] } },
    {
      name: 'desktop',
      dependencies: ['setup'],
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 900 },
        storageState: OPERATOR_STATE,
      },
    },
    {
      name: 'mobile',
      dependencies: ['setup'],
      use: { ...devices['Pixel 7'], storageState: OPERATOR_STATE },
    },
  ],
  webServer: [
    {
      command: 'uv run --package nazar-api nazar-api',
      cwd: REPO_ROOT,
      url: `http://127.0.0.1:${API_PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        NAZAR_ENV: 'test',
        NAZAR_API_PORT: String(API_PORT),
        NAZAR_STORAGE_DIR: `var/e2e-storage/${process.env.NAZAR_E2E_RUN}`,
        NAZAR_WEB_ORIGINS: `http://127.0.0.1:${WEB_PORT}`,
        NAZAR_DATABASE_URL: '',
        NAZAR_SECRET_KEY: '',
        NAZAR_WORKER_TOKEN: WORKER_TOKEN,
        NAZAR_WORKER_LEASE_SECONDS: '15',
        NAZAR_BOOTSTRAP_ADMIN_EMAIL: '',
        NAZAR_BOOTSTRAP_ADMIN_PASSWORD: '',
      },
    },
    // Two real worker processes, as in deployment (light worker + reconstruction worker), so
    // a long real reconstruction never blocks the quick test-pipeline specs.
    ...(['test', 'standard'] as const).map((mode) => ({
      // The test pipeline is paced so stage transitions and previews are observable.
      command:
        `uv run --package nazar-worker nazar-worker run --api http://127.0.0.1:${API_PORT} ` +
        `--modes ${mode} --worker-id e2e-${mode} --step-delay 0.8 --poll 0.5 --heartbeat 4 ` +
        '--env-file __none__',
      cwd: REPO_ROOT,
      wait: { stderr: new RegExp(`polling for ${mode} jobs`) },
      reuseExistingServer: false,
      timeout: 120_000,
      // Fast3R only when asked for (NAZAR_E2E_FAST3R=1 plus a configured GPU runtime), so a
      // developer's shell settings cannot silently change what the real-data spec checks.
      env: {
        NAZAR_WORKER_TOKEN: WORKER_TOKEN,
        ...(process.env.NAZAR_E2E_FAST3R === '1' ? {} : { NAZAR_FAST3R_PYTHON: '' }),
      },
    })),
    {
      command: `pnpm exec vite --port ${WEB_PORT} --strictPort --host 127.0.0.1`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: { NAZAR_API_PROXY_TARGET: `http://127.0.0.1:${API_PORT}` },
    },
  ],
});
