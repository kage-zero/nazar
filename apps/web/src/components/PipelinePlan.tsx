import { PIPELINE_STAGES, type StageName } from '@nazar/contracts';
import { Card, Tag } from './ui';

const STAGE_COPY: Record<StageName, { label: string; detail: string; optional: boolean }> = {
  preprocessing: {
    label: 'Ingest & keyframes',
    detail: 'Decode, score quality, select keyframes',
    optional: false,
  },
  geometry: {
    label: 'Multi-view geometry',
    detail: 'Camera poses + first point cloud',
    optional: false,
  },
  depth_priors: { label: 'Depth priors', detail: 'Monocular depth & normals', optional: true },
  dynamic_analysis: {
    label: 'Moving objects',
    detail: 'Detect, track and mask dynamics',
    optional: true,
  },
  sensor_optimization: {
    label: 'Sensor fusion',
    detail: 'Only when telemetry is supplied',
    optional: true,
  },
  dense_reconstruction: {
    label: 'Dense scene',
    detail: 'Filtered cloud + Gaussian scene',
    optional: false,
  },
  surface_processing: {
    label: 'Surface & geo',
    detail: 'Mesh and CRS where supported',
    optional: true,
  },
  analysis: { label: 'Confidence', detail: 'Observed / estimated / inferred', optional: false },
  exporting: { label: 'Export & report', detail: 'PLY, GLB, LAS, report', optional: false },
};

export function PipelinePlan() {
  return (
    <Card aria-labelledby="pipeline-heading">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="pipeline-heading" className="mono-label text-slate">
          Reconstruction pipeline
        </h2>
        <Tag tone="mist">No job yet</Tag>
      </div>
      <ol className="mt-4 grid gap-px overflow-hidden rounded-card-sm bg-mist sm:grid-cols-3">
        {PIPELINE_STAGES.map((stage, index) => {
          const copy = STAGE_COPY[stage];
          return (
            <li key={stage} className="flex flex-col gap-1 bg-paper p-4" data-stage={stage}>
              <span className="mono-label text-smoke">
                {String(index + 1).padStart(2, '0')}
                {copy.optional ? ' · optional' : ''}
              </span>
              <span className="font-medium">{copy.label}</span>
              <span className="text-sm text-slate">{copy.detail}</span>
            </li>
          );
        })}
      </ol>
      <p className="mt-4 text-sm text-slate">
        Stages are listed for orientation only: none of them runs in this build yet, and no progress
        is shown until a real job reports it.
      </p>
    </Card>
  );
}
