import { expect, test, type Page } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const SAMPLE_VIDEO = fileURLToPath(
  new URL('../../../docs/sample/video/sample1.mp4', import.meta.url),
);

function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', (err) => errors.push(err.message));
  return errors;
}

test('main screen renders with live API status and no console errors', async ({ page }) => {
  const errors = collectConsoleErrors(page);
  await page.goto('/');

  await expect(page.getByRole('heading', { level: 1 })).toHaveText(/one pass/i);
  await expect(page.getByRole('heading', { name: 'No missions yet' })).toBeVisible();

  // Real API: secrets are forced blank for E2E, so the API is up but honestly not ready.
  const status = page.getByTestId('api-status');
  await expect(status).toHaveAttribute('data-state', 'not-ready');
  await expect(status).toContainText('API online · not ready');

  const panel = page.getByTestId('readiness-panel');
  await expect(panel).toContainText('database');
  await expect(panel).toContainText('config:NAZAR_SECRET_KEY');
  await expect(panel).toContainText('Not configured · required');

  await expect(page.getByTestId('viewer-canvas').locator('canvas')).toBeVisible();
  await expect(page.getByTestId('viewer-empty')).toHaveText('No geometry yet.');

  await page.screenshot({ path: test.info().outputPath('main.png'), fullPage: true });
  expect(errors).toEqual([]);
});

test('API indicator reports offline when the health endpoint is unreachable', async ({ page }) => {
  await page.route('**/api/health', (route) => route.abort('connectionrefused'));
  await page.goto('/');
  const status = page.getByTestId('api-status');
  await expect(status).toHaveAttribute('data-state', 'offline');
  await expect(status).toContainText('API offline');
  await expect(page.getByTestId('readiness-panel')).toContainText('did not respond');
});

test('video picker accepts the sample video and rejects non-video files', async ({ page }) => {
  await page.goto('/');
  const input = page.getByTestId('video-input');

  await input.setInputFiles({
    name: 'notes.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('x'),
  });
  await expect(page.getByRole('alert')).toContainText('is not a video');

  await input.setInputFiles(SAMPLE_VIDEO);
  await expect(page.getByRole('alert')).toHaveCount(0);
  const summary = page.getByTestId('video-summary');
  await expect(summary).toContainText('sample1.mp4');
  await expect(summary).toContainText('2.0 MB');

  // Upload is not implemented yet, so the action must be disabled, not inert.
  await expect(page.getByRole('button', { name: 'Upload & validate' })).toBeDisabled();
});

test('viewer controls toggle layers and expose pressed state', async ({ page }) => {
  await page.goto('/');
  const grid = page.getByRole('button', { name: 'Grid' });
  await expect(grid).toHaveAttribute('aria-pressed', 'true');
  await grid.click();
  await expect(grid).toHaveAttribute('aria-pressed', 'false');
  await page.getByRole('button', { name: 'Reset view' }).click();
  await expect(page.getByTestId('viewer-canvas').locator('canvas')).toBeVisible();
});

test('keyboard users can skip to content and see focus', async ({ page, isMobile }) => {
  test.skip(isMobile, 'Keyboard navigation is checked on desktop.');
  await page.goto('/');
  await page.keyboard.press('Tab');
  const skip = page.getByRole('link', { name: 'Skip to content' });
  await expect(skip).toBeFocused();
  await expect(skip).toBeVisible();
});

test('layout has no horizontal overflow', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('api-status')).not.toHaveAttribute('data-state', 'checking');
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});
