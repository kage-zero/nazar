import type { Asset } from '@nazar/contracts';
import { API_BASE, ApiError, errorMessage, REQUEST_HEADER } from '../api/client';

export const CHUNK_BYTES = 8 * 1024 * 1024;
const MAX_ATTEMPTS = 4;

/** One chunk PUT. Resolves with the HTTP status and parsed JSON body. */
export type SendChunk = (
  assetId: string,
  offset: number,
  chunk: Blob,
  onBytes: (loaded: number) => void,
  signal: AbortSignal,
) => Promise<{ status: number; body: unknown }>;

export interface UploadOptions {
  onProgress: (sentBytes: number, totalBytes: number) => void;
  signal: AbortSignal;
  send?: SendChunk;
  chunkBytes?: number;
  sleep?: (ms: number) => Promise<void>;
}

const wait = (ms: number) =>
  new Promise<void>((resolve) => {
    setTimeout(resolve, ms);
  });

/** XHR rather than fetch: fetch cannot report upload progress in browsers. */
export const xhrSendChunk: SendChunk = (assetId, offset, chunk, onBytes, signal) =>
  new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', `${API_BASE}/api/assets/${assetId}/content?offset=${offset}`);
    xhr.withCredentials = true;
    xhr.setRequestHeader('X-Nazar-Request', REQUEST_HEADER['X-Nazar-Request']);
    xhr.setRequestHeader('Content-Type', 'application/octet-stream');
    xhr.upload.onprogress = (e) => {
      onBytes(e.loaded);
    };
    xhr.onload = () => {
      let body: unknown;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        body = undefined;
      }
      resolve({ status: xhr.status, body });
    };
    xhr.onerror = () => {
      reject(new Error('Network error while uploading.'));
    };
    const abort = () => {
      xhr.abort();
      reject(new DOMException('Upload cancelled.', 'AbortError'));
    };
    if (signal.aborted) {
      abort();
      return;
    }
    signal.addEventListener('abort', abort, { once: true });
    xhr.send(chunk);
  });

/**
 * Sends `file` in chunks. The server only accepts a chunk at the offset it has already
 * received up to, and answers a mismatch with 409 + its current offset, so a dropped
 * connection or a repeated chunk resumes from the right byte instead of corrupting data.
 * Transient failures (network, 5xx) are retried with backoff; 4xx errors are final.
 */
export async function uploadFile(
  assetId: string,
  file: Blob,
  startOffset: number,
  {
    onProgress,
    signal,
    send = xhrSendChunk,
    chunkBytes = CHUNK_BYTES,
    sleep = wait,
  }: UploadOptions,
): Promise<Asset> {
  let offset = startOffset;
  let failures = 0;
  let last: Asset | undefined;
  onProgress(offset, file.size);
  while (offset < file.size || last === undefined) {
    signal.throwIfAborted();
    const chunk = file.slice(offset, Math.min(offset + chunkBytes, file.size));
    let result: { status: number; body: unknown };
    try {
      result = await send(
        assetId,
        offset,
        chunk,
        (loaded) => {
          onProgress(offset + loaded, file.size);
        },
        signal,
      );
    } catch (error) {
      if (signal.aborted || ++failures >= MAX_ATTEMPTS) throw error;
      await sleep(500 * 2 ** failures);
      continue;
    }
    if (result.status === 200) {
      last = result.body as Asset;
      offset = last.received_bytes;
      failures = 0;
    } else if (result.status === 409 && isAsset(result.body)) {
      last = result.body;
      offset = last.received_bytes; // resume where the server actually is
    } else if (result.status >= 500 && ++failures < MAX_ATTEMPTS) {
      await sleep(500 * 2 ** failures);
      continue;
    } else {
      throw new ApiError(
        result.status,
        errorMessage(result.body, `Upload failed (${result.status}).`),
        result.body,
      );
    }
    onProgress(offset, file.size);
    if (last.status !== 'uploading') return last;
  }
  return last;
}

function isAsset(body: unknown): body is Asset {
  return !!body && typeof body === 'object' && 'received_bytes' in body && 'status' in body;
}
