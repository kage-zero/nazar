import type { UserPublic } from '@nazar/contracts';
import { useCallback, useEffect, useState } from 'react';
import { auth } from './missions';

export type Session =
  | { state: 'unknown' }
  | { state: 'setup' }
  | { state: 'signed-out' }
  | { state: 'signed-in'; user: UserPublic };

/** Tracks who is signed in. Re-checks whenever the API becomes reachable. */
export function useSession(apiReachable: boolean) {
  const [session, setSession] = useState<Session>({ state: 'unknown' });

  useEffect(() => {
    if (!apiReachable) return;
    const controller = new AbortController();
    auth
      .state(controller.signal)
      .then((state) => {
        setSession(
          state.user
            ? { state: 'signed-in', user: state.user }
            : { state: state.setup_required ? 'setup' : 'signed-out' },
        );
      })
      .catch(() => {
        if (!controller.signal.aborted) setSession({ state: 'unknown' });
      });
    return () => {
      controller.abort();
    };
  }, [apiReachable]);

  const signedIn = useCallback((user: UserPublic) => {
    setSession({ state: 'signed-in', user });
  }, []);

  const signOut = useCallback(async () => {
    await auth.logout();
    setSession({ state: 'signed-out' });
  }, []);

  return { session, signedIn, signOut };
}
