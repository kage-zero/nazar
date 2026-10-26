import { useId, useRef, useState, type DragEvent } from 'react';
import { checkVideoFile, formatBytes, VIDEO_EXTENSIONS, type VideoCheck } from '../lib/videoFile';
import { Button } from './ui';

const MAX_UPLOAD_BYTES = 2048 * 1024 * 1024;

/**
 * Upload component shell. It performs the client-side pre-check and shows file details.
 * Sending the file to the API is NOT implemented yet (Milestone 2), so the upload
 * action stays disabled and says so.
 */
export function VideoDropzone() {
  const inputId = useId();
  const hintId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [selection, setSelection] = useState<VideoCheck | null>(null);
  const [dragging, setDragging] = useState(false);

  const choose = (files: FileList | null) => {
    const file = files?.[0];
    setSelection(file ? checkVideoFile(file, MAX_UPLOAD_BYTES) : null);
  };

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setDragging(false);
    choose(event.dataTransfer.files);
  };

  return (
    <div className="flex flex-col gap-4">
      <label
        htmlFor={inputId}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => {
          setDragging(false);
        }}
        onDrop={onDrop}
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

      {selection && !selection.ok && (
        <p role="alert" className="rounded-button bg-carbon px-4 py-3 text-sm text-paper">
          {selection.error}
        </p>
      )}

      {selection?.ok && (
        <dl
          data-testid="video-summary"
          className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 font-mono text-xs"
        >
          <dt className="text-smoke uppercase">File</dt>
          <dd className="break-all">{selection.name}</dd>
          <dt className="text-smoke uppercase">Size</dt>
          <dd>{formatBytes(selection.sizeBytes)}</dd>
          <dt className="text-smoke uppercase">Type</dt>
          <dd>{selection.type}</dd>
        </dl>
      )}

      <div className="flex flex-col gap-1 rounded-card-sm bg-mist p-4">
        <span className="mono-label text-slate">Telemetry &amp; calibration · optional</span>
        <span className="text-sm text-slate">
          Video-only reconstruction stays in a local frame with unknown scale. Telemetry import
          arrives with the ingestion milestone.
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <Button disabled aria-describedby={`${inputId}-upload-note`}>
          Upload &amp; validate
        </Button>
        {selection && (
          <Button
            variant="ghost"
            onClick={() => {
              setSelection(null);
              if (inputRef.current) inputRef.current.value = '';
            }}
          >
            Clear
          </Button>
        )}
        <span id={`${inputId}-upload-note`} className="text-sm text-slate">
          Server upload is not built yet.
        </span>
      </div>
    </div>
  );
}
