import type { Mission } from '@nazar/contracts';
import { useId, useState, type SyntheticEvent } from 'react';
import { ApiError } from '../api/client';
import { Button, Card, Tag } from './ui';
import { TelemetryUpload } from './TelemetryUpload';
import { VideoUpload } from './VideoUpload';

const STATUS_TAG: Record<string, string> = {
  uploading: 'Upload paused',
  validating: 'Validating',
  ready: 'Ready',
  rejected: 'Rejected',
  failed: 'Failed',
};

function NewMission({
  onCreate,
  first,
}: {
  onCreate: (name: string) => Promise<void>;
  first: boolean;
}) {
  const inputId = useId();
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!name.trim()) {
      setError('Give the mission a name.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onCreate(name.trim());
      setName('');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not create the mission.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="flex flex-col gap-2" onSubmit={(e) => void submit(e)} noValidate>
      <label htmlFor={inputId} className="mono-label text-slate">
        {first ? 'Name your first mission' : 'New mission'}
      </label>
      <div className="flex flex-wrap gap-2">
        <input
          id={inputId}
          value={name}
          maxLength={120}
          placeholder="e.g. North quarry orbit"
          onChange={(e) => {
            setName(e.target.value);
          }}
          className="min-w-0 flex-1 rounded-button-sm border-[1.5px] border-ash bg-paper px-4 py-3 focus:border-carbon"
        />
        <Button type="submit" variant={first ? 'filled' : 'ghost'} disabled={busy}>
          Create
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-sm">
          {error}
        </p>
      )}
    </form>
  );
}

export function MissionPanel({
  list,
  selected,
  error,
  onSelect,
  onCreate,
  onChange,
}: {
  list: Mission[] | null;
  selected: Mission | null;
  error: string | null;
  onSelect: (id: string) => void;
  onCreate: (name: string) => Promise<void>;
  onChange: () => void;
}) {
  const selectId = useId();

  if (error) {
    return (
      <Card id="missions">
        <p role="alert">{error}</p>
      </Card>
    );
  }
  if (!list) {
    return (
      <Card id="missions" aria-busy="true">
        <p className="text-slate">Loading missions…</p>
      </Card>
    );
  }

  return (
    <Card id="missions" aria-labelledby="mission-heading">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="mission-heading" className="heading">
          {selected ? selected.name : 'No missions yet'}
        </h2>
        {selected?.video ? (
          <Tag tone={selected.video.status === 'ready' ? 'mint' : 'mist'}>
            {STATUS_TAG[selected.video.status] ?? selected.video.status}
          </Tag>
        ) : (
          <Tag tone="mist">{selected ? 'No video' : 'Empty'}</Tag>
        )}
      </div>

      {list.length > 1 && (
        <div className="mt-4 flex flex-col gap-1">
          <label htmlFor={selectId} className="mono-label text-slate">
            Mission
          </label>
          <select
            id={selectId}
            value={selected?.id ?? ''}
            onChange={(e) => {
              onSelect(e.target.value);
            }}
            className="rounded-button-sm border-[1.5px] border-ash bg-paper px-4 py-3"
          >
            {list.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="mt-6 flex flex-col gap-6">
        {selected ? (
          <>
            <VideoUpload key={selected.id} mission={selected} onChange={onChange} />
            <TelemetryUpload key={`t-${selected.id}`} mission={selected} onChange={onChange} />
          </>
        ) : (
          <p className="text-slate">
            A mission holds one drone video and everything NAZAR derives from it.
          </p>
        )}
        <NewMission onCreate={onCreate} first={list.length === 0} />
      </div>
    </Card>
  );
}
