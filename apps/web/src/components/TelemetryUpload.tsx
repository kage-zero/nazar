import type { Asset, Mission, TelemetrySummary } from '@nazar/contracts';
import { useEffect, useId, useRef, useState } from 'react';
import { ApiError } from '../api/client';
import { assets } from '../api/missions';
import {
  altitudeText,
  coverageText,
  TELEMETRY_EXTENSIONS,
  TELEMETRY_MAX_BYTES,
} from '../lib/telemetry';
import { uploadFile } from '../lib/upload';
import { formatBytes } from '../lib/videoFile';
import { Button, Tag } from './ui';

/** Optional flight log: attach, see what was accepted (and what it cannot do), remove. */
export function TelemetryUpload({ mission, onChange }: { mission: Mission; onChange: () => void }) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<{ id: string; summary: TelemetrySummary } | null>(null);
  const telemetry: Asset | null | undefined = mission.telemetry;
  const summary = loaded && loaded.id === telemetry?.id ? loaded.summary : null;
  const videoReady = mission.video?.status === 'ready';

  useEffect(() => {
    if (telemetry?.status !== 'ready') return;
    const abort = new AbortController();
    assets
      .telemetry(telemetry.id, abort.signal)
      .then((got) => {
        setLoaded({ id: telemetry.id, summary: got });
      })
      .catch(() => {
        if (!abort.signal.aborted) setError('Could not load the telemetry summary.');
      });
    return () => {
      abort.abort();
    };
    // The coverage depends on the video, so refresh when it becomes ready.
  }, [telemetry?.id, telemetry?.status, videoReady]);

  const attach = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    if (!TELEMETRY_EXTENSIONS.includes(ext)) {
      setError('Choose a DJI .SRT subtitle file or a .CSV flight log.');
      return;
    }
    if (file.size > TELEMETRY_MAX_BYTES) {
      setError(`Telemetry files are limited to ${formatBytes(TELEMETRY_MAX_BYTES)}.`);
      return;
    }
    setBusy(true);
    try {
      const asset = await assets.register(mission.id, file, 'telemetry');
      await uploadFile(asset.id, file, 0, {
        signal: new AbortController().signal,
        onProgress: () => undefined,
      });
      onChange();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'The telemetry upload failed.');
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  const remove = async () => {
    if (!telemetry) return;
    setBusy(true);
    try {
      await assets.remove(telemetry.id);
      onChange();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not remove the telemetry.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      aria-labelledby={`${inputId}-heading`}
      className="flex flex-col gap-3 rounded-card-sm bg-mist p-4"
      data-testid="telemetry"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={`${inputId}-heading`} className="mono-label text-slate">
          Flight telemetry · optional
        </h3>
        {telemetry?.status === 'ready' && <Tag tone="mint">Accepted</Tag>}
        {telemetry?.status === 'rejected' && <Tag>Rejected</Tag>}
      </div>

      {!telemetry && (
        <>
          <p className="text-sm text-slate">
            A DJI .SRT file (recorded next to the video) or a .CSV flight log lets NAZAR try to give
            the reconstruction a metric scale. It is used only if the camera path matches the GPS
            track; otherwise the result stays in a local frame with unknown scale.
          </p>
          <div>
            <label htmlFor={inputId} className="sr-only">
              Telemetry file
            </label>
            <input
              ref={inputRef}
              id={inputId}
              type="file"
              accept={TELEMETRY_EXTENSIONS.join(',')}
              disabled={busy}
              className="text-sm"
              onChange={(e) => void attach(e.target.files?.[0])}
            />
          </div>
        </>
      )}

      {telemetry?.status === 'rejected' && (
        <p className="text-sm" role="alert">
          {telemetry.filename}: {telemetry.error}
        </p>
      )}

      {telemetry?.status === 'ready' && summary && (
        <div className="flex flex-col gap-2 text-sm" data-testid="telemetry-summary">
          <p>
            <span className="font-medium">{telemetry.filename}</span> ·{' '}
            {summary.samples.toLocaleString()} positions at {summary.rate_hz} Hz ·{' '}
            {summary.start_s.toFixed(1)}–{summary.end_s.toFixed(1)} s ·{' '}
            {summary.horizontal_extent_m.toFixed(0)} m across
          </p>
          <p className="font-mono text-xs text-slate">
            {altitudeText(summary.altitude_kind)} · {coverageText(summary)}
            {Object.keys(summary.dropped).length > 0 &&
              ` · rejected ${Object.entries(summary.dropped)
                .map(([k, v]) => `${v} ${k.replaceAll('_', ' ')}`)
                .join(', ')}`}
          </p>
          <ul className="list-disc pl-5 text-slate">
            {summary.findings.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
          <p className="text-xs text-slate">Applies to jobs started from now on.</p>
        </div>
      )}

      {telemetry && telemetry.status !== 'uploading' && (
        <div>
          <Button variant="ghost" disabled={busy} onClick={() => void remove()}>
            Remove telemetry
          </Button>
        </div>
      )}

      {error && (
        <p role="alert" className="text-sm">
          {error}
        </p>
      )}
    </section>
  );
}
