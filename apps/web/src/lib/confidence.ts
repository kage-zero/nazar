import { Color } from 'three';

/**
 * Per-point confidence classes carried by final point clouds (PLY property `confidence`):
 * 1 = observed, 2 = estimated, 3 = inferred. The job report states the rule behind them;
 * they are heuristic labels, not calibrated probabilities.
 */
export const CONFIDENCE_CLASSES = [
  { code: 1, key: 'observed', label: 'Observed', hex: '#3987e5' },
  { code: 2, key: 'estimated', label: 'Estimated', hex: '#d95926' },
  { code: 3, key: 'inferred', label: 'Inferred', hex: '#8c8c8c' },
] as const;

export type ConfidenceKey = (typeof CONFIDENCE_CLASSES)[number]['key'];
export type ConfidenceCounts = Record<ConfidenceKey, number>;

/** Three's working (linear) colour space, matching what PLYLoader produces for vertex colours. */
function rgb(hex: string): [number, number, number] {
  const c = new Color(hex);
  return [c.r, c.g, c.b];
}

const UNKNOWN = rgb('#5a5a5a');
const BY_CODE = new Map<number, [number, number, number]>(
  CONFIDENCE_CLASSES.map((c) => [c.code, rgb(c.hex)]),
);

/** Vertex colours (linear RGB, 0..1) for each point's class. */
export function confidenceColors(classes: ArrayLike<number>): Float32Array {
  const out = new Float32Array(classes.length * 3);
  for (let i = 0; i < classes.length; i++) {
    out.set(BY_CODE.get(classes[i] ?? 0) ?? UNKNOWN, i * 3);
  }
  return out;
}

export function countConfidence(classes: ArrayLike<number>): ConfidenceCounts {
  const counts: ConfidenceCounts = { observed: 0, estimated: 0, inferred: 0 };
  for (let i = 0; i < classes.length; i++) {
    const match = CONFIDENCE_CLASSES.find((c) => c.code === classes[i]);
    if (match) counts[match.key] += 1;
  }
  return counts;
}
