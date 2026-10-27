export type Vec3 = [number, number, number];

export function distance(a: Vec3, b: Vec3): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

/**
 * A distance in the cloud's own units. With unknown scale it is relative only: compare it with
 * other distances in the same cloud, never with metres.
 */
export function distanceText(d: number, scaleStatus: string | undefined): string {
  const value = d >= 100 ? d.toFixed(0) : d >= 10 ? d.toFixed(1) : d.toFixed(2);
  if (scaleStatus === 'metric_sensor' || scaleStatus === 'metric_estimated') {
    return `${value} m${scaleStatus === 'metric_estimated' ? ' (estimated scale)' : ''}`;
  }
  return `${value} units (relative; scale unknown)`;
}

/** Next state of a two-point measurement after picking `p`: a third pick starts over. */
export function addPick(picks: Vec3[], p: Vec3): Vec3[] {
  return picks.length >= 2 ? [p] : [...picks, p];
}
