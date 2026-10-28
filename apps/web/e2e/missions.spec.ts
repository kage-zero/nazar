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

test('flight telemetry can be attached, summarised and removed', async ({ page }) => {
  // SYNTHETIC: a hand-written file in the DJI SRT layout (no real flight log was supplied).
  const cues = Array.from({ length: 12 }, (_, i) => {
    const t = `00:00:${String(i).padStart(2, '0')},000 --> 00:00:${String(i).padStart(2, '0')},033`;
    const lat = (41.89021 + i * 0.00009).toFixed(6);
    return `${i + 1}\n${t}\n[latitude: ${lat}] [longitude: 12.492231] [rel_alt: ${50 + i}.000 abs_alt: 98.5]\n`;
  });
  await createMission(page, 'With telemetry');
  const box = page.getByTestId('telemetry');
  await box.getByLabel('Telemetry file').setInputFiles({
    name: 'DJI_0001.SRT',
    mimeType: 'text/plain',
    buffer: Buffer.from(cues.join('\n')),
  });
  const summary = page.getByTestId('telemetry-summary');
  await expect(summary).toContainText('12 positions at 1 Hz');
  await expect(summary).toContainText('altitude above take-off');
  await expect(summary).toContainText('not sea-level');
  await expect(box).toContainText('Accepted');

  await box.getByRole('button', { name: 'Remove telemetry' }).click();
  await expect(box.getByLabel('Telemetry file')).toBeAttached();

  await box.getByLabel('Telemetry file').setInputFiles({
    name: 'log.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('time_s,latitude,longitude\n0,41.89,12.49\n'),
  });
  await expect(box.getByRole('alert')).toContainText('Fewer than two valid GPS positions');
  await expect(box).toContainText('Rejected');
});
