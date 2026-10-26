import type { Asset, Mission } from '@nazar/contracts';
import { useEffect, useId, useRef, useState, type DragEvent } from 'react';
import { ApiError } from '../api/client';
import { assets } from '../api/missions';
import { uploadFile } from '../lib/upload';
import { checkVideoFile, formatBytes, VIDEO_EXTENSIONS, type VideoCheck } from '../lib/videoFile';
import { Button, Tag } from './ui';

const MAX_UPLOAD_BYTES = 2048 * 1024 * 1024;

const PHASE_TEXT: Record<string, string> = {
  queued: 'Queued for validation',
  probing: 'Reading the container',
  analyzing: 'Decoding and scoring frames',
  selecting_keyframes: 'Choosing keyframes',
  extracting_keyframes: 'Extracting keyframe images',
};

type Transfer =
  | { state: 'idle' }
  | { state: 'sending'; sent: number; total: number }
  | { state: 'error'; message: string };

function Progress({
  label,
  value,
  max,
}: {
  label: string;
  value?: number | undefined;
  max?: number | undefined;
}) {
  const pct = value !== undefined && max ? Math.min(100, (value / max) * 100) : undefined;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex justify-between gap-4 text-sm">
        <span>{label}</span>
        {pct !== undefined && <span className="font-mono text-xs">{pct.toFixed(0)}%</span>}
      </div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct === undefined ? undefined : Math.round(pct)}
        className="h-2 overflow-hidden rounded-tag bg-mist"
      >
        <div
          className={`h-full rounded-tag bg-carbon transition-[width] ${pct === undefined ? 'w-1/3 animate-pulse' : ''}`}
          style={pct === undefined ? undefined : { width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

/** Choose → upload in resumable chunks → server validation with live progress. */
export function VideoUpload({ mission, onChange }: { mission: Mission; onChange: () => void }) {
  const inputId = useId();
  const hintId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const controller = useRef<AbortController | null>(null);
  const sendingId = useRef<string | null>(null);
  const [selection, setSelection] = useState<{ check: VideoCheck; file: File } | null>(null);
  const [dragging, setDragging] = useState(false);
  const [transfer, setTransfer] = useState<Transfer>({ state: 'idle' });
  const video: Asset | null | undefined = mission.video;

  useEffect(
    () => () => {
      controller.current?.abort();
    },
    [],
  );

  const choose = (files: FileList | null) => {
    const file = files?.[0];
    setTransfer({ state: 'idle' });
    setSelection(file ? { check: checkVideoFile(file, MAX_UPLOAD_BYTES), file } : null);
  };

  const clear = () => {
    setSelection(null);
    if (inputRef.current) inputRef.current.value = '';
  };

  // An earlier upload of this same file (name + size) that was interrupted can resume.
  const resumable =
    video?.status === 'uploading' && selection?.check.ok
      ? video.filename === selection.file.name && video.byte_size === selection.file.size
      : false;

  const start = async () => {
    if (!selection?.check.ok) return;
    const abort = new AbortController();
    controller.current = abort;
    const file = selection.file;
    setTransfer({ state: 'sending', sent: 0, total: file.size });
    try {
      if (video?.status === 'uploading' && !resumable) await assets.remove(video.id);
      const asset = resumable && video ? video : await assets.register(mission.id, file);
      sendingId.current = asset.id;
      await uploadFile(asset.id, file, asset.received_bytes, {
        signal: abort.signal,
        onProgress: (sent, total) => {
          setTransfer({ state: 'sending', sent, total });
        },
      });
      setTransfer({ state: 'idle' });
      clear();
    } catch (e) {
      if (abort.signal.aborted) {
        setTransfer({ state: 'idle' });
      } else {
        setTransfer({
          state: 'error',
          message: e instanceof ApiError ? e.message : 'The connection dropped. Retry to resume.',
        });
      }
    } finally {
      controller.current = null;
      onChange();
    }
  };

  const cancelUpload = async () => {
    controller.current?.abort();
    if (sendingId.current) await assets.remove(sendingId.current).catch(() => undefined);
    sendingId.current = null;
    onChange();
  };

  const removeVideo = async () => {
    if (video) await assets.remove(video.id).catch(() => undefined);
    onChange();
  };

  if (transfer.state === 'sending') {
    return (
      <div className="flex flex-col gap-4" data-testid="upload-progress">
        <Progress
          label={`Uploading ${formatBytes(transfer.sent)} of ${formatBytes(transfer.total)}`}
          value={transfer.sent}
          max={transfer.total}
        />
        <Button variant="ghost" className="self-start" onClick={() => void cancelUpload()}>
          Cancel upload
        </Button>
      </div>
    );
  }

  if (video?.status === 'validating') {
    const p = video.progress;
    return (
      <div className="flex flex-col gap-4" data-testid="validation-progress">
        <span className="font-mono text-xs break-all">{video.filename}</span>
        <Progress
          label={PHASE_TEXT[p?.phase ?? 'queued'] ?? 'Validating'}
          value={p?.completed ?? undefined}
          max={p?.total ?? undefined}
        />
        <p className="text-sm text-slate">
          The server decodes every frame to check it is a real, usable video. This runs on the CPU.
        </p>
        <Button variant="ghost" className="self-start" onClick={() => void removeVideo()}>
          Cancel validation
        </Button>
      </div>
    );
  }

  if (video?.status === 'ready') {
    return (
      <div className="flex flex-wrap items-center justify-between gap-4" data-testid="video-ready">
        <div className="flex min-w-0 flex-col gap-1">
          <Tag className="self-start">Video validated</Tag>
          <span className="font-mono text-xs break-all">
            {video.filename} · {formatBytes(video.byte_size)}
          </span>
        </div>
        <Button variant="ghost" onClick={() => void removeVideo()}>
          Replace video
        </Button>
      </div>
    );
  }

  const failed = video?.status === 'rejected' || video?.status === 'failed';

  return (
    <div className="flex flex-col gap-4">
      {failed && (
        <div role="alert" className="flex flex-col gap-3 rounded-card-sm bg-carbon p-4 text-paper">
          <span className="mono-label text-mint">
            {video.status === 'rejected' ? 'Video rejected' : 'Validation failed'}
          </span>
          <span className="text-sm">
            {video.filename}: {video.error}
          </span>
          <div className="flex flex-wrap gap-2">
            {video.status === 'failed' && (
              <Button
                variant="ghost-inverted"
                onClick={() => void assets.retry(video.id).then(onChange)}
              >
                Retry validation
              </Button>
            )}
            <Button variant="ghost-inverted" onClick={() => void removeVideo()}>
              Remove
            </Button>
          </div>
        </div>
      )}

      {video?.status === 'uploading' && (
        <p className="rounded-card-sm bg-mint p-4 text-sm" data-testid="upload-interrupted">
          An upload of <span className="font-mono text-xs">{video.filename}</span> stopped at{' '}
          {formatBytes(video.received_bytes)} of {formatBytes(video.byte_size)}. Choose the same
          file to resume, or any other video to start over.
        </p>
      )}

      {!failed && (
        <label
          htmlFor={inputId}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => {
            setDragging(false);
          }}
          onDrop={(event: DragEvent<HTMLLabelElement>) => {
            event.preventDefault();
            setDragging(false);
            choose(event.dataTransfer.files);
          }}
          className={`flex cursor-pointer flex-col items-start gap-2 rounded-card-sm border-[1.5px] border-dashed p-6 transition-colors focus-within:border-carbon ${
            dragging ? 'border-carbon bg-mint' : 'border-ash bg-mist hover:border-slate'
          }`}
        >
          <span className="mono-label text-slate">Drone video · required</span>
          <span className="text-lg font-medium">Drop one video here, or browse</span>
          <span id={hintId} className="text-sm text-slate">
            {VIDEO_EXTENSIONS.join(', ').toUpperCase()} up to {formatBytes(MAX_UPLOAD_BYTES)}. The
            server re-checks the file by decoding it.
          </span>
          <input
            ref={inputRef}
            id={inputId}
            type="file"
            accept={`video/*,${VIDEO_EXTENSIONS.map((e) => `.${e}`).join(',')}`}
            aria-describedby={hintId}
            className="sr-only"
            data-testid="video-input"
            onChange={(e) => {
              choose(e.target.files);
            }}
          />
        </label>
      )}

      {selection && !selection.check.ok && (
        <p role="alert" className="rounded-button bg-carbon px-4 py-3 text-sm text-paper">
          {selection.check.error}
        </p>
      )}

      {selection?.check.ok && (
        <dl
          data-testid="video-summary"
          className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 font-mono text-xs"
        >
          <dt className="text-smoke uppercase">File</dt>
          <dd className="break-all">{selection.check.name}</dd>
          <dt className="text-smoke uppercase">Size</dt>
          <dd>{formatBytes(selection.check.sizeBytes)}</dd>
          <dt className="text-smoke uppercase">Type</dt>
          <dd>{selection.check.type}</dd>
        </dl>
      )}

      {transfer.state === 'error' && (
        <p role="alert" className="rounded-button bg-carbon px-4 py-3 text-sm text-paper">
          {transfer.message}
        </p>
      )}

      {!failed && (
        <div className="flex flex-wrap items-center gap-4">
          <Button disabled={!selection?.check.ok} onClick={() => void start()}>
            {transfer.state === 'error' || resumable ? 'Resume upload' : 'Upload & validate'}
          </Button>
          {selection && (
            <Button variant="ghost" onClick={clear}>
              Clear
            </Button>
          )}
        </div>
      )}

      <div className="flex flex-col gap-1 rounded-card-sm bg-mist p-4">
        <span className="mono-label text-slate">Telemetry &amp; calibration · optional</span>
        <span className="text-sm text-slate">
          Video-only reconstruction stays in a local frame with unknown scale. Telemetry import is
          not built yet.
        </span>
      </div>
    </div>
  );
}
