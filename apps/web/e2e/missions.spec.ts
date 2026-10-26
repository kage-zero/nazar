import { expect, test } from '@playwright/test';
import { collectConsoleErrors, createMission, SAMPLE_VIDEO } from './helpers';
import { OPERATOR } from './operator';

test('sample video uploads, validates and shows the preflight report', async ({ page }) => {
  // Server-side validation decodes every frame; leave room for a loaded machine.
  test.setTimeout(120_000);
  const errors = collectConsoleErrors(page);
  await createMission(page, 'Colosseum');

  await page.getByTestId('video-input').setInputFiles(SAMPLE_VIDEO);
  await expect(page.getByTestId('video-summary')).toContainText('sample1.mp4');
  await page.getByRole('button', { name: 'Upload & validate' }).click();

  await expect(page.getByTestId('video-ready')).toBeVisible({ timeout: 90_000 });
  const report = page.getByTestId('preflight-panel');
  await expect(report).toContainText('Usable for reconstruction');
  await expect(report).toContainText('Duration');
  await expect(page.getByTestId('preflight-warnings')).toContainText('No telemetry');
  await expect(page.getByTestId('quality-chart').locator('svg path')).toHaveCount(1);

  const strip = page.getByTestId('keyframe-strip');
  expect(await strip.getByRole('img').count()).toBeGreaterThanOrEqual(8);
  const first = strip.getByRole('img').first();
  await first.scrollIntoViewIfNeeded();
  await expect
    .poll(() => first.evaluate((img: HTMLImageElement) => img.naturalWidth))
    .toBeGreaterThan(0);

  await page.screenshot({ path: test.info().outputPath('preflight.png'), fullPage: true });
  expect(errors).toEqual([]);
});

test('client rejects non-video files before uploading', async ({ page }) => {
  await createMission(page, 'Wrong type');
  await page.getByTestId('video-input').setInputFiles({
    name: 'notes.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('x'),
  });
  await expect(page.getByRole('alert')).toContainText('is not a video');
  await expect(page.getByRole('button', { name: 'Upload & validate' })).toBeDisabled();
});

test('a corrupt video is rejected by the server and can be removed', async ({ page }) => {
  test.setTimeout(90_000);
  await createMission(page, 'Corrupt');
  await page.getByTestId('video-input').setInputFiles({
    name: 'broken.mp4',
    mimeType: 'video/mp4',
    buffer: Buffer.from('definitely not an mp4 stream '.repeat(200)),
  });
  await page.getByRole('button', { name: 'Upload & validate' }).click();
  const alert = page.getByRole('alert');
  await expect(alert).toContainText('Video rejected', { timeout: 60_000 });
  await alert.getByRole('button', { name: 'Remove' }).click();
  await expect(page.getByTestId('video-input')).toBeAttached();
});

test.describe('signed out', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test('operator signs in, sees missions, and signs out', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();

    await page.getByLabel('Email').fill(OPERATOR.email);
    await page.getByLabel('Password').fill('not-the-password');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByRole('alert')).toContainText('incorrect');

    await page.getByLabel('Password').fill(OPERATOR.password);
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();

    await page.getByRole('button', { name: 'Sign out' }).click();
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  });
});
