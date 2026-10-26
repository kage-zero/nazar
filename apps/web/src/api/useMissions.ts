import type { Mission } from '@nazar/contracts';
import { useCallback, useEffect, useState } from 'react';
import { missions as api } from './missions';

const POLL_MS = 1000;
const PARAM = 'mission';

/** The selected mission lives in the URL so a reload or shared link reopens it. */
function missionFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get(PARAM);
}

function writeMissionToUrl(id: string | null) {
  const url = new URL(window.location.href);
  if (id) url.searchParams.set(PARAM, id);
  else url.searchParams.delete(PARAM);
  window.history.replaceState(null, '', url);
}

/** The signed-in operator's missions, the selected one, and live validation polling. */
export function useMissions(enabled: boolean) {
  const [list, setList] = useState<Mission[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(missionFromUrl);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback((signal?: AbortSignal) => {
    api
      .list(signal)
      .then((rows) => {
        setList(rows);
        setError(null);
        setSelectedId((id) => (id && rows.some((m) => m.id === id) ? id : (rows[0]?.id ?? null)));
      })
      .catch(() => {
        if (!signal?.aborted) setError('Missions could not be loaded.');
      });
  }, []);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    load(controller.signal);
    return () => {
      controller.abort();
    };
  }, [enabled, load]);

  useEffect(() => {
    if (enabled && list) writeMissionToUrl(selectedId);
  }, [enabled, list, selectedId]);

  const visible = enabled ? list : null;
  const selected = visible?.find((m) => m.id === selectedId) ?? null;
  const validating = selected?.video?.status === 'validating';

  useEffect(() => {
    if (!validating || !selectedId) return;
    const timer = setInterval(() => {
      api
        .get(selectedId)
        .then((m) => {
          setList((rows) => rows?.map((r) => (r.id === m.id ? m : r)) ?? rows);
        })
        .catch(() => undefined);
    }, POLL_MS);
    return () => {
      clearInterval(timer);
    };
  }, [validating, selectedId]);

  const create = useCallback(async (name: string) => {
    const mission = await api.create(name);
    setList((rows) => [mission, ...(rows ?? [])]);
    setSelectedId(mission.id);
  }, []);

  return { list: visible, selected, select: setSelectedId, create, refresh: load, error };
}
