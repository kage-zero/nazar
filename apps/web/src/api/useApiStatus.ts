import { useEffect, useState } from 'react';
import { fetchApiStatus, type ApiStatus } from './system';

const POLL_MS = 15_000;

/** Polls API liveness/readiness; re-checks immediately when the tab regains focus. */
export function useApiStatus(): ApiStatus {
  const [status, setStatus] = useState<ApiStatus>({ state: 'checking' });

  useEffect(() => {
    let controller = new AbortController();
    const check = () => {
      controller.abort();
      controller = new AbortController();
      fetchApiStatus(controller.signal).then(setStatus, () => undefined);
    };
    check();
    const timer = window.setInterval(check, POLL_MS);
    window.addEventListener('focus', check);
    return () => {
      controller.abort();
      window.clearInterval(timer);
      window.removeEventListener('focus', check);
    };
  }, []);

  return status;
}
