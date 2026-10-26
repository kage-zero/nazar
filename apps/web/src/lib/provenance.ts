import type { ArtifactManifest } from '@nazar/contracts';

export type GeometryMethod = 'fast3r' | 'cpu-baseline' | 'test' | 'other';

/** Which geometry method produced an artifact, from its provenance (never from the pipeline name:
 * the standard pipeline falls back from Fast3R to the CPU baseline at run time). */
export function geometryMethod(artifact: ArtifactManifest): GeometryMethod {
  const { producer, test_pipeline } = artifact.provenance;
  if (test_pipeline) return 'test';
  if (producer.endsWith('/fast3r')) return 'fast3r';
  if (producer.endsWith('/sfm-baseline')) return 'cpu-baseline';
  return 'other';
}

/** The method of the newest artifact that says so, or null before any output exists. */
export function jobMethod(artifacts: ArtifactManifest[]): GeometryMethod | null {
  for (const artifact of [...artifacts].reverse()) {
    const m = geometryMethod(artifact);
    if (m !== 'other') return m;
  }
  return null;
}

export const METHOD_TAG: Record<GeometryMethod, string> = {
  fast3r: 'GPU · Fast3R',
  'cpu-baseline': 'CPU baseline',
  test: 'Test pipeline',
  other: 'Reconstruction',
};

/** Viewer badge: says what the geometry is, not just who made it. */
export function sourceText(cloud: ArtifactManifest | null): string {
  if (!cloud) return 'No geometry';
  switch (geometryMethod(cloud)) {
    case 'fast3r':
      return 'Fast3R · learned dense geometry';
    case 'cpu-baseline':
      return 'CPU baseline · sparse SfM';
    case 'test':
      return 'Test pipeline · synthetic scene';
    default:
      return cloud.provenance.model ?? 'Reconstruction';
  }
}
