import type { JobEvent } from '@nazar/contracts';

export type StreamState = 'connecting' | 'live' | 'reconnecting' | 'closed';

/** The subset of WebSocket the stream uses, so tests can drive it without a server. */
export interface SocketLike {
  onopen: (() => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onclose: ((ev: { code: number }) => void) | null;
  close: () => void;
}

export interface StreamDeps {
  openSocket: (url: string) => SocketLike;
  fetchEvents: (after: number) => Promise<JobEvent[]>;
  schedule: (fn: () => void, ms: number) => () => void;
}

const TERMINAL_EVENTS = new Set(['job.completed', 'job.failed', 'job.cancelled']);
const MAX_BACKOFF_MS = 8000;

/**
 * Live job events over WebSocket, with REST catch-up between reconnects.
 *
 * The server keeps every event, so nothing is lost while disconnected: on an unexpected close
 * the stream fetches missed events over REST, then reopens the socket from the newest `seq`
 * (with exponential backoff). Close code 1000 means the server delivered a terminal event.
 * Consumers still deduplicate by `seq`; this class only tries not to send duplicates.
 */
export class JobStream {
  private socket: SocketLike | null = null;
  private cancelTimer: (() => void) | null = null;
  private failures = 0;
  private stopped = false;

  constructor(
    private readonly url: (after: number) => string,
    private cursor: number,
    private readonly onEvent: (event: JobEvent) => void,
    private readonly onState: (state: StreamState) => void,
    private readonly deps: StreamDeps,
  ) {}

  start() {
    this.open();
  }

  stop() {
    this.stopped = true;
    this.cancelTimer?.();
    const socket = this.socket;
    this.socket = null;
    if (socket) {
      socket.onclose = null;
      socket.close();
    }
  }

  private deliver(event: JobEvent): boolean {
    if (event.seq <= this.cursor) return false;
    this.cursor = event.seq;
    this.onEvent(event);
    return TERMINAL_EVENTS.has(event.type);
  }

  private open() {
    if (this.stopped) return;
    this.onState(this.failures === 0 ? 'connecting' : 'reconnecting');
    const socket = this.deps.openSocket(this.url(this.cursor));
    this.socket = socket;
    socket.onopen = () => {
      this.failures = 0;
      this.onState('live');
    };
    socket.onmessage = (ev) => {
      if (typeof ev.data !== 'string') return;
      try {
        this.deliver(JSON.parse(ev.data) as JobEvent);
      } catch {
        // A malformed frame is dropped; the REST catch-up after reconnect covers any gap.
      }
    };
    socket.onclose = (ev) => {
      this.socket = null;
      if (this.stopped) return;
      if (ev.code === 1000 || ev.code === 4404) {
        this.onState('closed');
        return;
      }
      this.failures += 1;
      this.onState('reconnecting');
      void this.catchUp();
    };
  }

  private async catchUp() {
    let finished = false;
    try {
      for (const event of await this.deps.fetchEvents(this.cursor)) {
        if (this.stopped) return;
        finished = this.deliver(event) || finished;
      }
    } catch {
      // Offline or API down: keep retrying on the backoff schedule.
    }
    if (this.stopped) return;
    if (finished) {
      this.onState('closed');
      return;
    }
    const delay = Math.min(500 * 2 ** (this.failures - 1), MAX_BACKOFF_MS);
    this.cancelTimer = this.deps.schedule(() => {
      this.cancelTimer = null;
      this.open();
    }, delay);
  }
}

export function streamUrl(jobId: string, after: number): string {
  const { protocol, host } = window.location;
  const scheme = protocol === 'https:' ? 'wss' : 'ws';
  return `${scheme}://${host}/api/jobs/${jobId}/stream?after=${after}`;
}

/** Adapts a browser WebSocket to `SocketLike`. */
export function browserSocket(url: string): SocketLike {
  const ws = new WebSocket(url);
  const like: SocketLike = {
    onopen: null,
    onmessage: null,
    onclose: null,
    close: () => {
      ws.close();
    },
  };
  ws.onopen = () => like.onopen?.();
  ws.onmessage = (ev: MessageEvent) => like.onmessage?.({ data: ev.data });
  ws.onclose = (ev: CloseEvent) => like.onclose?.({ code: ev.code });
  return like;
}
