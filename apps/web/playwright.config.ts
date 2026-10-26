import { defineConfig, devices } from '@playwright/test';

const REPO_ROOT = '../..';
const API_PORT = 8765;
const WEB_PORT = 5174;

/**
 * Fast deterministic E2E profile: real FastAPI + real Vite dev server, no GPU, no weights.
 * The API runs with an isolated storage dir and secrets forced blank so readiness is
 * deterministic regardless of what the developer has put in their local .env.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
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
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
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
        NAZAR_STORAGE_DIR: 'var/e2e-storage',
        NAZAR_WEB_ORIGINS: `http://127.0.0.1:${WEB_PORT}`,
        NAZAR_DATABASE_URL: '',
        NAZAR_SECRET_KEY: '',
        NAZAR_WORKER_TOKEN: '',
        NAZAR_BOOTSTRAP_ADMIN_EMAIL: '',
        NAZAR_BOOTSTRAP_ADMIN_PASSWORD: '',
      },
    },
    {
      command: `pnpm exec vite --port ${WEB_PORT} --strictPort --host 127.0.0.1`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: { NAZAR_API_PROXY_TARGET: `http://127.0.0.1:${API_PORT}` },
    },
  ],
});
