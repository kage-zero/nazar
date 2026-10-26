import type { FrameFlag, FrameSeries } from '@nazar/contracts';

export interface QualityPoint {
  t: number;
  /** Sharpness relative to the clip median (1 = typical frame). */
  rel: number;
  flags: FrameFlag[];
}

export interface FlagRun {
  start: number;
  end: number;
}

/**
 * Reduces a per-frame series to at most `maxPoints` buckets for drawing. Each bucket
 * keeps its *minimum* relative sharpness so blur dips stay visible after downsampling,
 * and the union of its flags.
 */
export function qualityPoints(series: FrameSeries, median: number, maxPoints = 480) {
  const n = series.t.length;
  const size = Math.max(1, Math.ceil(n / maxPoints));
  const points: QualityPoint[] = [];
  for (let start = 0; start < n; start += size) {
    let rel = Infinity;
    const flags = new Set<FrameFlag>();
    for (let i = start; i < Math.min(n, start + size); i++) {
      rel = Math.min(rel, median > 0 ? (series.sharpness[i] ?? 0) / median : 0);
      for (const f of series.flags[i] ?? []) flags.add(f);
    }
    points.push({ t: series.t[start] ?? 0, rel, flags: [...flags] });
  }
  return points;
}

/** Contiguous time ranges where any frame carries a flag. */
export function flaggedRuns(points: QualityPoint[], end: number): FlagRun[] {
  const runs: FlagRun[] = [];
  let open: number | null = null;
  points.forEach((p, i) => {
    if (p.flags.length > 0 && open === null) open = p.t;
    if (p.flags.length === 0 && open !== null) {
      runs.push({ start: open, end: p.t });
      open = null;
    }
    if (i === points.length - 1 && open !== null) runs.push({ start: open, end });
  });
  return runs;
}

/** Index of the point nearest to time `t` (points are sorted by time). */
export function nearestIndex(points: QualityPoint[], t: number): number {
  let lo = 0;
  let hi = points.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if ((points[mid]?.t ?? 0) < t) lo = mid + 1;
    else hi = mid;
  }
  const prev = points[lo - 1];
  return prev && Math.abs(prev.t - t) < Math.abs((points[lo]?.t ?? 0) - t) ? lo - 1 : lo;
}
