import type { ComputeTarget, WorkerPresence } from '@nazar/contracts';

/** Which GPU worker runs a job. The choice is remembered per browser; the job keeps its own. */

const KEY = 'nazar.compute';

export const COMPUTE_LABEL: Record<ComputeTarget, string> = {
  local: 'Local GPU',
  college: 'College GPU',
};

export function loadCompute(): ComputeTarget {
  try {
    return window.localStorage.getItem(KEY) === 'college' ? 'college' : 'local';
  } catch {
    return 'local';
  }
}

export function saveCompute(target: ComputeTarget) {
  try {
    window.localStorage.setItem(KEY, target);
  } catch {
    // A convenience only; the toggle still works for this page view.
  }
}

/** One line on whether the chosen worker is there to pick a job up. */
export function presenceText(target: ComputeTarget, presence: WorkerPresence | undefined): string {
  const name = target === 'local' ? 'Local GPU worker (this laptop)' : 'College GPU worker';
  if (!presence?.online) {
    const how =
      target === 'local'
        ? 'start it with `pnpm worker`'
        : 'start it in the VDI with `nazar-worker run --location college`, or use bundle mode';
    return `${name}: offline. Jobs wait in the queue until it connects (${how}).`;
  }
  const method =
    presence.geometry === 'fast3r'
      ? 'Fast3R on its GPU'
      : presence.geometry === 'cpu-baseline'
        ? 'CPU baseline (no Fast3R runtime)'
        : 'method not reported yet';
  return `${name}: online · ${method}.`;
}
