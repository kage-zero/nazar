import { expect, test } from '@playwright/test';
import { collectConsoleErrors, createMission, uploadSample } from './helpers';

// TEST-PIPELINE MODE: the real API, worker process, event stream and artifact routes run
// end to end, but the worker emits a fixed synthetic scene. This proves the plumbing and the
// progressive viewer, not reconstruction quality.

test('test pipeline streams stages and a preview before completing', async ({ page }) => {
  test.setTimeout(180_000);
  const errors = collectConsoleErrors(page);
  await createMission(page, 'Pipeline');
  await uploadSample(page);

  const panel = page.getByTestId('job-panel');
  await panel.getByRole('button', { name: 'Run test pipeline' }).click();
  await expect(panel.getByText('Test pipeline', { exact: true })).toBeVisible();
  await expect(panel.getByRole('button', { name: 'Reconstruct' })).toHaveCount(0);

  // A preview is rendered while the job is still running: progressive, not all-at-once.
  await page.waitForFunction(
    () => {
      const stage = document.querySelector('[data-testid="viewer-stage"]');
      const status = document.querySelector('[data-testid="job-status"]');
      return (
        stage?.getAttribute('data-cloud-kind') === 'point_cloud_preview' &&
        Number(stage.getAttribute('data-cloud-points')) > 0 &&
        status?.getAttribute('data-status') !== 'completed'
      );
    },
    undefined,
    { timeout: 90_000 },
  );
  await expect(page.getByTestId('completion-feedback')).toHaveCount(0);

  const status = page.getByTestId('job-status');
  await expect(status).toHaveAttribute('data-status', 'completed', { timeout: 60_000 });
  const viewer = page.getByTestId('viewer-stage');
  await expect(viewer).toHaveAttribute('data-cloud-kind', 'point_cloud');
  await expect(page.getByTestId('viewer-loaded')).toContainText('Final cloud');
  await expect(page.getByText('Test pipeline · synthetic scene')).toBeVisible();

  const pipeline = page.getByTestId('pipeline');
  await expect(pipeline.locator('[data-stage="geometry"]')).toHaveAttribute(
    'data-state',
    'completed',
  );
  const sensor = pipeline.locator('[data-stage="sensor_optimization"]');
  await expect(sensor).toHaveAttribute('data-state', 'skipped');
  await expect(sensor).toContainText('No telemetry');
  await expect(page.getByTestId('job-warnings')).toContainText('not your video');

  const outputs = page.getByTestId('job-outputs');
  await expect(outputs).toContainText('Point cloud');
  await expect(outputs).toContainText('Camera path');
  await expect(outputs).toContainText('Processing report');
  const href = await outputs
    .locator('li', { hasText: /^Point cloudrev/ })
    .getByRole('link', { name: 'Download' })
    .getAttribute('href');
  expect(href).toBeTruthy();
  const download = await page.request.get(href ?? '');
  expect(download.status()).toBe(200);
  expect((await download.body()).subarray(0, 4).toString()).toBe('ply\n');

  // Layer toggles and fit work while a cloud is present.
  const points = page.getByRole('button', { name: 'Points' });
  await points.click();
  await expect(points).toHaveAttribute('aria-pressed', 'false');
  await points.click();
  await page.getByRole('button', { name: 'Fit' }).click();
  await expect(page.getByRole('button', { name: 'Camera path' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );

  await page.screenshot({ path: test.info().outputPath('job-complete.png'), fullPage: true });
  expect(errors).toEqual([]);
});

test('a running job survives a reload, can be cancelled and retried', async ({ page }) => {
  test.setTimeout(180_000);
  await createMission(page, 'Cancel');
  await uploadSample(page);
  const panel = page.getByTestId('job-panel');
  await panel.getByRole('button', { name: 'Run test pipeline' }).click();
  const status = page.getByTestId('job-status');
  await expect(status).toContainText('Running', { timeout: 60_000 });

  // Reconnect: the job is reloaded from the server and the stream resumes.
  await page.reload();
  const mission = page.locator('#missions');
  await expect(mission).toBeVisible();
  await expect(status).toBeVisible();
  await expect(status).not.toHaveAttribute('data-status', 'queued');

  await panel.getByRole('button', { name: 'Cancel job' }).click();
  await expect(status).toHaveAttribute('data-status', 'cancelled', { timeout: 30_000 });
  await expect(panel.getByRole('button', { name: 'Retry' })).toBeVisible();

  await panel.getByRole('button', { name: 'Retry' }).click();
  await expect(status).toHaveAttribute('data-status', 'completed', { timeout: 90_000 });
});
