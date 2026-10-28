export type Vec3 = [number, number, number];

export function distance(a: Vec3, b: Vec3): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

export interface FrameScale {
  scale_status: string;
  metres_per_unit?: number | null;
}

function fixed(d: number): string {
  return d >= 100 ? d.toFixed(0) : d >= 10 ? d.toFixed(1) : d.toFixed(2);
}

/**
 * A distance in the cloud's own units. With unknown scale it is relative only: compare it with
 * other distances in the same cloud, never with metres. A sensor scale (metres per local unit,
 * from the GNSS alignment) converts it to metres, labelled as an estimate.
 */
export function distanceText(d: number, frame: FrameScale | null | undefined): string {
  const status = frame?.scale_status;
  if (status === 'metric_sensor' || status === 'metric_estimated') {
    const metres = d * (frame?.metres_per_unit ?? 1);
    const source = status === 'metric_sensor' ? 'GNSS scale, estimate' : 'estimated scale';
    return `${fixed(metres)} m (${source})`;
  }
  return `${fixed(d)} units (relative; scale unknown)`;
}

/** Next state of a two-point measurement after picking `p`: a third pick starts over. */
export function addPick(picks: Vec3[], p: Vec3): Vec3[] {
  return picks.length >= 2 ? [p] : [...picks, p];
}
