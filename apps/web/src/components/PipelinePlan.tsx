import {
  PIPELINE_STAGES,
  type Job,
  type StageName,
  type StageRunState,
  type StageState,
} from '@nazar/contracts';
import { Card, Tag } from './ui';

export const STAGE_COPY: Record<StageName, { label: string; detail: string; optional: boolean }> = {
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

const STATE_TEXT: Record<StageRunState, string> = {
  pending: 'Pending',
  running: 'Running',
  completed: 'Done',
  skipped: 'Skipped',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

function progressText(state: StageState): string | null {
  const p = state.progress;
  if (!p) return null;
  if (p.total != null && p.completed != null) {
    const unit = p.unit ? ` ${p.unit}` : '';
    return `${p.message} · ${p.completed.toLocaleString()} / ${p.total.toLocaleString()}${unit}`;
  }
  return p.message;
}

/** Pipeline stages, live when a job exists. Skips show their reason; nothing is invented. */
export function PipelinePlan({ job }: { job: Job | null }) {
  const states = new Map(job?.stages.map((s) => [s.stage, s]));
  return (
    <Card aria-labelledby="pipeline-heading" data-testid="pipeline">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="pipeline-heading" className="mono-label text-slate">
          Reconstruction pipeline
        </h2>
        <Tag tone="mist">{job ? `Attempt ${String(job.attempt)}` : 'No job yet'}</Tag>
      </div>
      <ol className="mt-4 grid gap-px overflow-hidden rounded-card-sm bg-mist sm:grid-cols-3">
        {PIPELINE_STAGES.map((stage, index) => {
          const copy = STAGE_COPY[stage];
          const state = states.get(stage);
          const run = state?.state ?? 'pending';
          const detail = state ? (state.reason ?? progressText(state)) : null;
          return (
            <li
              key={stage}
              className={`flex flex-col gap-1 p-4 transition-colors duration-300 motion-reduce:transition-none ${
                run === 'running' ? 'bg-mint' : 'bg-paper'
              }`}
              data-stage={stage}
              data-state={run}
            >
              <span className="mono-label flex justify-between gap-2 text-smoke">
                <span>
                  {String(index + 1).padStart(2, '0')}
                  {copy.optional ? ' · optional' : ''}
                </span>
                {job && (
                  <span className={run === 'pending' ? '' : 'text-carbon'}>{STATE_TEXT[run]}</span>
                )}
              </span>
              <span className={`font-medium ${run === 'skipped' ? 'text-slate' : ''}`}>
                {copy.label}
              </span>
              <span className="text-sm text-slate">{detail ?? copy.detail}</span>
              {state?.duration_s != null && (
                <span className="font-mono text-xs text-slate">
                  {state.duration_s.toFixed(1)} s
                </span>
              )}
            </li>
          );
        })}
      </ol>
      {!job && (
        <p className="mt-4 text-sm text-slate">
          Stages are listed for orientation. Progress appears only when a job reports it.
        </p>
      )}
    </Card>
  );
}
