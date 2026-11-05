import { FPS } from '@nazar/contracts';
import { clampFps } from './sampling';

/** The frame rate last chosen in this browser; the default (1 fps) until the user changes it. */
const KEY = 'nazar.fps';

export function loadFps(): number {
  try {
    const stored = Number(window.localStorage.getItem(KEY));
    return stored > 0 ? clampFps(stored) : FPS.default;
  } catch {
    return FPS.default;
  }
}

export function saveFps(fps: number) {
  try {
    window.localStorage.setItem(KEY, String(fps));
  } catch {
    // A convenience only; the choice still applies to this page view.
  }
}
