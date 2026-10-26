import type { PreflightReport } from '@nazar/contracts';
import { useEffect, useMemo, useRef, useState, type PointerEvent } from 'react';
import { flaggedRuns, nearestIndex, qualityPoints } from '../lib/qualitySeries';

const MIN_W = 280;
const H = 180;
const PAD = { top: 12, right: 12, bottom: 28, left: 36 };
const Y_MAX = 2.5;
const FLAG_TEXT = {
  blurry: 'blurry',
  dark: 'dark',
  overexposed: 'over-exposed',
  duplicate: 'repeat',
};

/**
 * Sharpness over time, relative to the clip's median frame. One series, so no legend:
 * flagged stretches are shaded bands and keyframes are ticks under the axis (shape, not
 * colour, carries meaning). Hover or focus + arrow keys to read exact values.
 */
export function QualityChart({ report }: { report: PreflightReport }) {
  const { series, summary, probe, keyframes } = report;
  const duration = Math.max(series.t.at(-1) ?? 0, probe.duration_s, 0.001);
  const points = useMemo(
    () => qualityPoints(series, summary.median_sharpness),
    [series, summary.median_sharpness],
  );
  const runs = useMemo(() => flaggedRuns(points, duration), [points, duration]);
  const blurLine = Number(report.settings.blur_relative ?? 0.4);
  const [active, setActive] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  // Draw in real pixels (viewBox = rendered size) so 10px labels stay 10px at any width.
  const [W, setW] = useState(640);
  useEffect(() => {
    const box = boxRef.current;
    if (!box) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setW(Math.max(MIN_W, Math.round(entry.contentRect.width)));
    });
    observer.observe(box);
    return () => {
      observer.disconnect();
    };
  }, []);

  const x = (t: number) => PAD.left + (t / duration) * (W - PAD.left - PAD.right);
  const y = (rel: number) =>
    PAD.top + (1 - Math.min(rel, Y_MAX) / Y_MAX) * (H - PAD.top - PAD.bottom);
  const baseline = H - PAD.bottom;
  const path = points
    .map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(p.rel).toFixed(1)}`)
    .join('');

  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    const box = svgRef.current?.getBoundingClientRect();
    if (!box) return;
    const sx = ((e.clientX - box.left) / box.width) * W;
    const t = ((sx - PAD.left) / (W - PAD.left - PAD.right)) * duration;
    setActive(nearestIndex(points, Math.max(0, Math.min(duration, t))));
  };

  const point = active === null ? undefined : points[active];
  const tipLeft = point ? (x(point.t) / W) * 100 : 0;

  return (
    <figure className="flex flex-col gap-2" data-testid="quality-chart">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="mono-label text-slate">Sharpness over time · × clip median</span>
        <span className="mono-label text-smoke">shaded = flagged frames · ticks = keyframes</span>
      </figcaption>
      <div className="relative" ref={boxRef}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          className="block h-auto w-full touch-none select-none"
          role="img"
          aria-label={`Frame sharpness over ${duration.toFixed(1)} seconds. ${summary.blurry_frames} blurry, ${summary.duplicate_frames} repeated, ${keyframes.length} keyframes. Use arrow keys to step through.`}
          tabIndex={0}
          onPointerMove={onMove}
          onPointerLeave={() => {
            setActive(null);
          }}
          onKeyDown={(e) => {
            if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
            e.preventDefault();
            const step = e.key === 'ArrowRight' ? 1 : -1;
            setActive((a) => Math.max(0, Math.min(points.length - 1, (a ?? -step) + step)));
          }}
          onBlur={() => {
            setActive(null);
          }}
        >
          {runs.map((r) => (
            <rect
              key={r.start}
              x={x(r.start)}
              y={PAD.top}
              width={Math.max(1, x(r.end) - x(r.start))}
              height={baseline - PAD.top}
              fill="var(--color-ash)"
              opacity={0.55}
            />
          ))}
          {[0, 1, 2].map((v) => (
            <g key={v}>
              <line
                x1={PAD.left}
                x2={W - PAD.right}
                y1={y(v)}
                y2={y(v)}
                stroke="var(--color-mist)"
                strokeWidth={1}
              />
              <text
                x={PAD.left - 6}
                y={y(v) + 4}
                textAnchor="end"
                className="fill-smoke font-mono text-[10px]"
              >
                {v}×
              </text>
            </g>
          ))}
          <line
            x1={PAD.left}
            x2={W - PAD.right}
            y1={y(blurLine)}
            y2={y(blurLine)}
            stroke="var(--color-slate)"
            strokeDasharray="4 4"
            strokeWidth={1}
          />
          <text
            x={W - PAD.right}
            y={y(blurLine) - 4}
            textAnchor="end"
            className="fill-slate font-mono text-[10px]"
          >
            blur threshold
          </text>
          <path
            d={path}
            fill="none"
            stroke="var(--color-carbon)"
            strokeWidth={2}
            strokeLinejoin="round"
          />
          {keyframes.map((k) => (
            <line
              key={k.index}
              x1={x(k.t)}
              x2={x(k.t)}
              y1={baseline + 4}
              y2={baseline + 12}
              stroke="var(--color-carbon)"
              strokeWidth={2}
              strokeLinecap="round"
            />
          ))}
          <text x={PAD.left} y={H - 2} className="fill-smoke font-mono text-[10px]">
            0 s
          </text>
          <text
            x={W - PAD.right}
            y={H - 2}
            textAnchor="end"
            className="fill-smoke font-mono text-[10px]"
          >
            {duration.toFixed(1)} s
          </text>
          {point && (
            <g pointerEvents="none">
              <line
                x1={x(point.t)}
                x2={x(point.t)}
                y1={PAD.top}
                y2={baseline}
                stroke="var(--color-slate)"
                strokeWidth={1}
              />
              <circle
                cx={x(point.t)}
                cy={y(point.rel)}
                r={4}
                fill="var(--color-carbon)"
                stroke="var(--color-paper)"
                strokeWidth={2}
              />
            </g>
          )}
        </svg>
        {point && (
          <div
            role="status"
            className="pointer-events-none absolute top-0 rounded-button-sm bg-carbon px-3 py-2 font-mono text-xs whitespace-nowrap text-paper"
            style={{
              left: `${tipLeft}%`,
              transform: `translateX(${tipLeft > 60 ? 'calc(-100% - 8px)' : '8px'})`,
            }}
          >
            <div>{point.t.toFixed(2)} s</div>
            <div>{point.rel.toFixed(2)}× median sharpness</div>
            {point.flags.length > 0 && (
              <div className="text-mint">{point.flags.map((f) => FLAG_TEXT[f]).join(', ')}</div>
            )}
          </div>
        )}
      </div>
    </figure>
  );
}
