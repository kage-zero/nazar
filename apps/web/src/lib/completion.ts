/**
 * Completion feedback: a short locally synthesised tone and a vibration, each optional,
 * each at most once per job id. Visible status text always carries the same information.
 */

const NOTIFIED_KEY = 'nazar.completed-jobs';
const PREFS_KEY = 'nazar.feedback';

export interface FeedbackPrefs {
  sound: boolean;
  haptics: boolean;
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function loadPrefs(): FeedbackPrefs {
  try {
    const raw = storage()?.getItem(PREFS_KEY);
    const parsed = raw ? (JSON.parse(raw) as Partial<FeedbackPrefs>) : {};
    return { sound: parsed.sound ?? true, haptics: parsed.haptics ?? true };
  } catch {
    return { sound: true, haptics: true };
  }
}

export function savePrefs(prefs: FeedbackPrefs) {
  try {
    storage()?.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    // Preferences are a convenience; failing to persist them is harmless.
  }
}

/** Returns true the first time it is called for `jobId` (per browser), false afterwards. */
export function claimCompletion(jobId: string, store: Storage | null = storage()): boolean {
  let seen: string[] = [];
  try {
    seen = JSON.parse(store?.getItem(NOTIFIED_KEY) ?? '[]') as string[];
  } catch {
    seen = [];
  }
  if (seen.includes(jobId)) return false;
  try {
    store?.setItem(NOTIFIED_KEY, JSON.stringify([...seen.slice(-49), jobId]));
  } catch {
    // Without storage we can still dedupe within this page via the caller's state.
  }
  return true;
}

export const hapticsSupported = () =>
  typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function';

function playTone(): boolean {
  const Ctx = window.AudioContext as typeof AudioContext | undefined;
  if (!Ctx) return false;
  try {
    const ctx = new Ctx();
    // Autoplay policy: a context created without a user gesture may stay suspended.
    if (ctx.state === 'suspended') {
      void ctx.close();
      return false;
    }
    const now = ctx.currentTime;
    const gain = ctx.createGain();
    gain.connect(ctx.destination);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.15, now + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.5);
    for (const [freq, at] of [
      [660, 0],
      [990, 0.12],
    ] as const) {
      const osc = ctx.createOscillator();
      osc.type = 'sine';
      osc.frequency.value = freq;
      osc.connect(gain);
      osc.start(now + at);
      osc.stop(now + 0.5);
    }
    setTimeout(() => void ctx.close(), 800);
    return true;
  } catch {
    return false;
  }
}

/** What actually happened, so the UI never claims a sound or vibration that did not run. */
export interface CompletionFeedback {
  sound: boolean;
  haptics: boolean;
}

export function celebrate(prefs: FeedbackPrefs): CompletionFeedback {
  const sound = prefs.sound && playTone();
  const haptics = prefs.haptics && hapticsSupported() && navigator.vibrate([40, 60, 40]);
  return { sound, haptics };
}
