import type { JobEvent } from '@nazar/contracts';
import { describe, expect, it } from 'vitest';
import { JobStream, type SocketLike, type StreamState } from './jobStream';

function ev(seq: number, type: JobEvent['type'] = 'cancel.requested'): JobEvent {
  return { job_id: 'j', seq, ts: 'x', status: 'queued', type } as JobEvent;
}

class FakeSocket implements SocketLike {
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  onclose: ((ev: { code: number }) => void) | null = null;
  closed = false;
  constructor(readonly url: string) {}
  close() {
    this.closed = true;
  }
  push(event: JobEvent) {
    this.onmessage?.({ data: JSON.stringify(event) });
  }
}

function harness(rest: JobEvent[] = []) {
  const sockets: FakeSocket[] = [];
  const timers: { fn: () => void; ms: number }[] = [];
  const seen: number[] = [];
  const states: StreamState[] = [];
  const stream = new JobStream(
    (after) => `ws://x/stream?after=${String(after)}`,
    2,
    (e) => seen.push(e.seq),
    (s) => states.push(s),
    {
      openSocket: (url) => {
        const s = new FakeSocket(url);
        sockets.push(s);
        return s;
      },
      fetchEvents: (after) => Promise.resolve(rest.filter((e) => e.seq > after)),
      schedule: (fn, ms) => {
        timers.push({ fn, ms });
        return () => undefined;
      },
    },
  );
  return { stream, sockets, timers, seen, states };
}

const flush = () =>
  new Promise((resolve) => {
    setTimeout(resolve, 0);
  });

describe('JobStream', () => {
  it('delivers live events once, in order, from the starting cursor', () => {
    const h = harness();
    h.stream.start();
    expect(h.sockets[0]?.url).toBe('ws://x/stream?after=2');
    h.sockets[0]?.onopen?.();
    h.sockets[0]?.push(ev(2));
    h.sockets[0]?.push(ev(3));
    h.sockets[0]?.push(ev(3));
    h.sockets[0]?.push(ev(4));
    expect(h.seen).toEqual([3, 4]);
    expect(h.states).toEqual(['connecting', 'live']);
  });

  it('catches up over REST after a drop and reconnects from the new cursor', async () => {
    const h = harness([ev(3), ev(4), ev(5)]);
    h.stream.start();
    h.sockets[0]?.onopen?.();
    h.sockets[0]?.push(ev(3));
    h.sockets[0]?.onclose?.({ code: 1006 });
    await flush();
    expect(h.seen).toEqual([3, 4, 5]);
    expect(h.timers[0]?.ms).toBe(500);
    h.timers[0]?.fn();
    expect(h.sockets[1]?.url).toBe('ws://x/stream?after=5');
    expect(h.states).toContain('reconnecting');
  });

  it('stops after a normal close or once REST shows a terminal event', async () => {
    const normal = harness();
    normal.stream.start();
    normal.sockets[0]?.onclose?.({ code: 1000 });
    expect(normal.states.at(-1)).toBe('closed');

    const finished = harness([ev(3, 'job.completed')]);
    finished.stream.start();
    finished.sockets[0]?.onclose?.({ code: 1006 });
    await flush();
    expect(finished.seen).toEqual([3]);
    expect(finished.timers).toHaveLength(0);
    expect(finished.states.at(-1)).toBe('closed');
  });

  it('stop() closes the socket without reconnecting', () => {
    const h = harness();
    h.stream.start();
    h.stream.stop();
    expect(h.sockets[0]?.closed).toBe(true);
    expect(h.timers).toHaveLength(0);
  });
});
