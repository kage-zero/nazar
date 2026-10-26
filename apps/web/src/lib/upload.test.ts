import type { Asset } from '@nazar/contracts';
import { describe, expect, it } from 'vitest';
import { ApiError } from '../api/client';
import { uploadFile, type SendChunk } from './upload';

const asset = (received: number, size: number): Asset => ({
  id: 'a1',
  mission_id: 'm1',
  kind: 'video',
  filename: 'pass.mp4',
  byte_size: size,
  received_bytes: received,
  status: received === size ? 'validating' : 'uploading',
  error: null,
  progress: null,
  sha256: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
});

/** In-memory server that enforces the same offset rule as the API. */
function fakeServer(size: number, faults: ('network' | 500)[] = []) {
  let received = 0;
  const calls: number[] = [];
  const send: SendChunk = (_id, offset, chunk, onBytes) => {
    calls.push(offset);
    const fault = faults.shift();
    if (fault === 'network') return Promise.reject(new Error('Network error while uploading.'));
    if (fault === 500) return Promise.resolve({ status: 500, body: { detail: 'boom' } });
    if (offset !== received) return Promise.resolve({ status: 409, body: asset(received, size) });
    onBytes(chunk.size);
    received += chunk.size;
    return Promise.resolve({ status: 200, body: asset(received, size) });
  };
  return { send, calls };
}

const options = (send: SendChunk, progress: number[] = []) => ({
  send,
  chunkBytes: 4,
  signal: new AbortController().signal,
  sleep: () => Promise.resolve(),
  onProgress: (sent: number) => progress.push(sent),
});

describe('uploadFile', () => {
  it('sends the file in order and reports monotonic progress', async () => {
    const server = fakeServer(10);
    const progress: number[] = [];
    const result = await uploadFile(
      'a1',
      new Blob(['0123456789']),
      0,
      options(server.send, progress),
    );
    expect(result.status).toBe('validating');
    expect(server.calls).toEqual([0, 4, 8]);
    expect(progress.at(-1)).toBe(10);
    expect([...progress].sort((a, b) => a - b)).toEqual(progress);
  });

  it('retries transient failures and resumes at the server offset', async () => {
    const server = fakeServer(10, ['network', 500]);
    const result = await uploadFile('a1', new Blob(['0123456789']), 0, options(server.send));
    expect(result.received_bytes).toBe(10);
  });

  it('follows a 409 to the offset the server already has', async () => {
    const server = fakeServer(10);
    await uploadFile('a1', new Blob(['0123']), 0, { ...options(server.send), chunkBytes: 4 });
    const result = await uploadFile('a1', new Blob(['0123456789']), 0, options(server.send));
    expect(result.received_bytes).toBe(10);
    expect(server.calls).toEqual([0, 0, 4, 8]);
  });

  it('stops on a client error with the server message', async () => {
    const send: SendChunk = () =>
      Promise.resolve({ status: 413, body: { detail: 'Chunk exceeds the declared size.' } });
    const error: unknown = await uploadFile('a1', new Blob(['01']), 0, options(send)).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(413);
    expect((error as ApiError).message).toBe('Chunk exceeds the declared size.');
  });

  it('honours cancellation', async () => {
    const controller = new AbortController();
    controller.abort();
    const server = fakeServer(10);
    await expect(
      uploadFile('a1', new Blob(['0123456789']), 0, {
        ...options(server.send),
        signal: controller.signal,
      }),
    ).rejects.toThrow();
    expect(server.calls).toEqual([]);
  });
});
