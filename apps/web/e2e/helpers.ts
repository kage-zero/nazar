import { expect, type Page } from '@playwright/test';
import { fileURLToPath } from 'node:url';

export const SAMPLE_VIDEO = fileURLToPath(
  new URL('../../../docs/sample/video/sample1.mp4', import.meta.url),
);

export function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', (err) => errors.push(err.message));
  return errors;
}

/** Creates a uniquely named mission and leaves it selected. Tests run in parallel. */
export async function createMission(page: Page, label: string): Promise<string> {
  const name = `${label} ${test_id()}`;
  await page.goto('/');
  const form = page.locator('#missions form');
  await form.getByRole('textbox').fill(name);
  await form.getByRole('button', { name: 'Create' }).click();
  await expect(page.getByRole('heading', { name })).toBeVisible();
  return name;
}

/** Uploads the sample video to the selected mission and waits for validation to finish. */
export async function uploadSample(page: Page): Promise<void> {
  await page.getByTestId('video-input').setInputFiles(SAMPLE_VIDEO);
  await page.getByRole('button', { name: 'Upload & validate' }).click();
  await expect(page.getByTestId('video-ready')).toBeVisible({ timeout: 90_000 });
}

let counter = 0;
function test_id() {
  counter += 1;
  return `${process.pid}-${counter}-${Date.now() % 100000}`;
}
