import { lazy, Suspense } from 'react';
import { sourceText } from '../lib/provenance';
import { useViewerStore } from '../state/viewerStore';
import { Button, Card, Tag } from './ui';

const ViewerScene = lazy(() => import('./ViewerScene'));

const FRAME_TEXT = {
  local_reconstruction: 'Local',
  enu: 'ENU',
  ecef: 'ECEF',
  geographic: 'Geographic',
  projected: 'Projected',
} as const;

const SCALE_TEXT = {
  unknown: 'unknown scale',
  relative: 'relative scale',
  metric_estimated: 'metric (estimated)',
  metric_sensor: 'metric (sensor)',
} as const;

export function Viewport() {
  const s = useViewerStore();
  const { cloud, path, loaded } = s;
  const kindText = loaded?.kind === 'point_cloud' ? 'Final cloud' : 'Preview';

  return (
    <Card
      inverted
      id="viewer"
      aria-labelledby="viewer-heading"
      className="flex min-h-[420px] flex-col gap-4 lg:min-h-[560px]"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="viewer-heading" className="mono-label text-smoke">
          3D viewer
        </h2>
        <Tag tone="mint">{sourceText(cloud)}</Tag>
      </div>

      <div
        className="relative min-h-[380px] flex-1 overflow-hidden rounded-card-sm bg-carbon"
        data-testid="viewer-stage"
        data-cloud-kind={loaded?.kind ?? ''}
        data-cloud-revision={loaded?.revision ?? 0}
        data-cloud-points={loaded?.points ?? 0}
      >
        <Suspense fallback={<p className="mono-label p-6 text-smoke">Loading 3D engine…</p>}>
          <ViewerScene />
        </Suspense>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex flex-col gap-1 p-4">
          {loaded ? (
            <p
              className="font-mono text-xs text-smoke"
              aria-live="polite"
              data-testid="viewer-loaded"
            >
              {kindText} · revision {loaded.revision} · {loaded.points.toLocaleString()} points
            </p>
          ) : (
            <>
              <p className="text-lg font-medium text-paper" data-testid="viewer-empty">
                No geometry yet.
              </p>
              <p className="max-w-md text-sm text-smoke">
                Point clouds appear here as soon as a job publishes its first one. The grid and axes
                are reference aids, not data.
              </p>
            </>
          )}
          {s.layerError && (
            <p role="alert" className="text-sm text-paper">
              {s.layerError}
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <dl className="flex flex-wrap gap-x-6 gap-y-1 font-mono text-xs">
          <div className="flex gap-2">
            <dt className="text-smoke uppercase">Frame</dt>
            <dd>{cloud?.frame ? FRAME_TEXT[cloud.frame.type] : 'Local · none'}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="text-smoke uppercase">Units</dt>
            <dd>
              {cloud?.frame
                ? `${cloud.frame.units}, ${SCALE_TEXT[cloud.frame.scale_status]}`
                : 'Unknown'}
            </dd>
          </div>
        </dl>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Viewer controls">
          {cloud && (
            <Button variant="ghost-inverted" aria-pressed={s.showCloud} onClick={s.toggleCloud}>
              Points
            </Button>
          )}
          {path && (
            <Button variant="ghost-inverted" aria-pressed={s.showPath} onClick={s.togglePath}>
              Camera path
            </Button>
          )}
          <Button variant="ghost-inverted" aria-pressed={s.showGrid} onClick={s.toggleGrid}>
            Grid
          </Button>
          <Button variant="ghost-inverted" aria-pressed={s.showAxes} onClick={s.toggleAxes}>
            Axes
          </Button>
          {cloud && (
            <Button variant="ghost-inverted" onClick={s.requestFit}>
              Fit
            </Button>
          )}
          <Button variant="ghost-inverted" onClick={s.requestReset}>
            Reset view
          </Button>
        </div>
      </div>
    </Card>
  );
}
