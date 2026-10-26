import type { ApiStatus } from '../api/system';
import { Tag } from './ui';

const LABEL: Record<ApiStatus['state'], string> = {
  checking: 'API checking…',
  offline: 'API offline',
  'not-ready': 'API online · not ready',
  ready: 'API ready',
};

export function ApiStatusBadge({ status }: { status: ApiStatus }) {
  const tone = status.state === 'ready' ? 'mint' : status.state === 'offline' ? 'carbon' : 'mist';
  return (
    <div role="status" aria-live="polite" data-testid="api-status" data-state={status.state}>
      <Tag tone={tone}>
        <span
          aria-hidden="true"
          className={
            status.state === 'not-ready'
              ? 'size-2 rounded-full bg-voltage outline outline-1 outline-carbon'
              : 'size-2 rounded-full bg-current'
          }
        />
        {LABEL[status.state]}
      </Tag>
    </div>
  );
}
