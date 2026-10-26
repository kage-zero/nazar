import { lazy, Suspense } from 'react';
import { useViewerStore } from '../state/viewerStore';
import { Button, Card, Tag } from './ui';

const ViewerScene = lazy(() => import('./ViewerScene'));

export function Viewport() {
  const { showGrid, showAxes, toggleGrid, toggleAxes, requestReset } = useViewerStore();

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
        <Tag tone="mint">Viewport scaffold</Tag>
      </div>

      <div className="relative min-h-[380px] flex-1 overflow-hidden rounded-card-sm bg-carbon">
        <Suspense fallback={<p className="mono-label p-6 text-smoke">Loading 3D engine…</p>}>
          <ViewerScene />
        </Suspense>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex flex-col gap-1 p-4">
          <p className="text-lg font-medium text-paper" data-testid="viewer-empty">
            No geometry yet.
          </p>
          <p className="max-w-md text-sm text-smoke">
            Point clouds appear here as soon as the first real reconstruction stage produces them.
            The grid and axes are reference aids, not data.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <dl className="flex flex-wrap gap-x-6 gap-y-1 font-mono text-xs">
          <div className="flex gap-2">
            <dt className="text-smoke uppercase">Frame</dt>
            <dd>Local · none</dd>
          </div>
          <div className="flex gap-2">
            <dt className="text-smoke uppercase">Units</dt>
            <dd>Unknown</dd>
          </div>
        </dl>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Viewer controls">
          <Button variant="ghost-inverted" aria-pressed={showGrid} onClick={toggleGrid}>
            Grid
          </Button>
          <Button variant="ghost-inverted" aria-pressed={showAxes} onClick={toggleAxes}>
            Axes
          </Button>
          <Button variant="ghost-inverted" onClick={requestReset}>
            Reset view
          </Button>
        </div>
      </div>
    </Card>
  );
}
