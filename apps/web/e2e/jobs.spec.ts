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

// REAL DATA: the supplied drone clip through the real preflight and real geometry: the CPU
// baseline (classical structure-from-motion) by default, Fast3R on the GPU when the run sets
// NAZAR_E2E_FAST3R=1 (see playwright.config.ts). Nothing here is synthetic.
const FAST3R = process.env.NAZAR_E2E_FAST3R === '1';
test('reconstruct builds real geometry from the sample video, progressively', async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'CPU-heavy; one viewport is enough.');
  test.setTimeout(300_000);
  const errors = collectConsoleErrors(page);
  await createMission(page, 'Real');
  await uploadSample(page);

  const panel = page.getByTestId('job-panel');
  await panel.getByRole('button', { name: 'Reconstruct' }).click();

  // A real preview cloud arrives while the job is still running.
  await page.waitForFunction(
    () => {
      const stage = document.querySelector('[data-testid="viewer-stage"]');
      const status = document.querySelector('[data-testid="job-status"]');
      return (
        stage?.getAttribute('data-cloud-kind') === 'point_cloud_preview' &&
        Number(stage.getAttribute('data-cloud-points')) > 500 &&
        status?.getAttribute('data-status') !== 'completed'
      );
    },
    undefined,
    { timeout: 200_000 },
  );
  // Labels come from the artifacts' provenance: they name the method that actually ran.
  await expect(
    panel.getByText(FAST3R ? 'GPU · Fast3R' : 'CPU baseline', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(FAST3R ? 'Fast3R · learned dense geometry' : 'CPU baseline · sparse SfM'),
  ).toBeVisible();

  const status = page.getByTestId('job-status');
  await expect(status).toHaveAttribute('data-status', 'completed', { timeout: 200_000 });
  const viewer = page.getByTestId('viewer-stage');
  await expect(viewer).toHaveAttribute('data-cloud-kind', 'point_cloud');
  const finalPoints = Number(await viewer.getAttribute('data-cloud-points'));
  expect(finalPoints).toBeGreaterThan(FAST3R ? 50_000 : 3000);

  const pipeline = page.getByTestId('pipeline');
  await expect(pipeline.locator('[data-stage="geometry"]')).toHaveAttribute(
    'data-state',
    'completed',
  );
  await expect(pipeline.locator('[data-stage="depth_priors"]')).toHaveAttribute(
    'data-state',
    'skipped',
  );
  await expect(page.getByTestId('job-warnings')).toContainText('distances are relative');

  // The report is real JSON describing the geometry that was produced.
  const href = await page
    .getByTestId('job-outputs')
    .locator('li', { hasText: /^Processing report/ })
    .getByRole('link', { name: 'Download' })
    .getAttribute('href');
  const report = (await (await page.request.get(href ?? '')).json()) as {
    geometry_method: string;
    geometry: {
      registered_keyframes?: number;
      placed_keyframes?: number;
      points: number;
      mean_reproj_px?: number;
    };
    coordinate_frame: { scale_status: string };
    confidence: { observed: number; estimated: number };
  };
  expect(report.geometry_method).toBe(FAST3R ? 'fast3r' : 'sfm');
  if (FAST3R) {
    expect(report.geometry.placed_keyframes).toBeGreaterThanOrEqual(18);
  } else {
    expect(report.geometry.registered_keyframes).toBeGreaterThanOrEqual(18);
    expect(report.geometry.mean_reproj_px).toBeLessThan(1.5);
  }
  // The report describes the cloud the viewer shows (the filtered one), not the raw output.
  expect(report.geometry.points).toBe(finalPoints);
  expect(report.coordinate_frame.scale_status).toBe('unknown');

  // The final cloud carries per-point confidence classes; the legend counts match the report.
  const toggle = page.getByRole('button', { name: 'Colour by confidence' });
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  const legend = page.getByTestId('confidence-legend');
  await expect(legend).toContainText(
    `Estimated ${report.confidence.estimated.toLocaleString('en-US')}`,
  );
  if (report.confidence.observed > 0) {
    await expect(legend).toContainText(
      `Observed ${report.confidence.observed.toLocaleString('en-US')}`,
    );
  }
  await page.screenshot({
    path: testInfo.outputPath('reconstruct-confidence.png'),
    fullPage: true,
  });
  await toggle.click();
  await expect(legend).toHaveCount(0);

  await page.screenshot({ path: testInfo.outputPath('reconstruct-complete.png'), fullPage: true });
  expect(errors).toEqual([]);
});
