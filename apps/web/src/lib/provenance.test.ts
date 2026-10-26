import type { ArtifactManifest } from '@nazar/contracts';
import { describe, expect, it } from 'vitest';
import { jobMethod, sourceText } from './provenance';

function artifact(producer: string, test_pipeline = false): ArtifactManifest {
  return { provenance: { producer, test_pipeline, model: 'M' } } as unknown as ArtifactManifest;
}

describe('provenance labels', () => {
  it('names the method that actually ran', () => {
    expect(sourceText(artifact('nazar-worker/fast3r'))).toBe('Fast3R · learned dense geometry');
    expect(sourceText(artifact('nazar-worker/sfm-baseline'))).toBe('CPU baseline · sparse SfM');
    expect(sourceText(artifact('x', true))).toBe('Test pipeline · synthetic scene');
    expect(sourceText(artifact('someone/else'))).toBe('M');
    expect(sourceText(null)).toBe('No geometry');
  });

  it('takes the job method from its newest artifact, unknown before any output', () => {
    expect(jobMethod([])).toBeNull();
    expect(jobMethod([artifact('nazar-worker/fast3r')])).toBe('fast3r');
    // A Fast3R preview followed by a fallback: the newest output wins.
    expect(
      jobMethod([artifact('nazar-worker/fast3r'), artifact('nazar-worker/sfm-baseline')]),
    ).toBe('cpu-baseline');
  });
});
