import type { ApiStatus } from '../api/system';
import { Card, Tag } from './ui';

const STATUS_TEXT: Record<string, string> = {
  ok: 'OK',
  degraded: 'Degraded',
  unavailable: 'Unavailable',
  not_configured: 'Not configured',
  not_implemented: 'Not built yet',
};

export function ReadinessPanel({ status }: { status: ApiStatus }) {
  return (
    <Card aria-labelledby="system-heading" data-testid="readiness-panel">
      <div className="flex items-center justify-between gap-4">
        <h2 id="system-heading" className="mono-label text-slate">
          System readiness
        </h2>
        {status.state !== 'checking' && status.state !== 'offline' && (
          <span className="mono-label text-smoke">v{status.health.version}</span>
        )}
      </div>
      {status.state === 'checking' && <p className="mt-4 text-slate">Contacting the API…</p>}
      {status.state === 'offline' && (
        <p className="mt-4 text-slate">
          {status.reason} Start it with <code className="font-mono text-sm">pnpm dev</code> and this
          panel will update automatically.
        </p>
      )}
      {(status.state === 'ready' || status.state === 'not-ready') && (
        <ul className="mt-4 divide-y divide-mist">
          {status.readiness.checks.map((check) => (
            <li
              key={check.name}
              className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2"
            >
              <span className="font-mono text-xs break-all text-carbon">{check.name}</span>
              <Tag
                tone={check.status === 'ok' ? 'mint' : 'mist'}
                className={check.required && check.status !== 'ok' ? 'text-carbon' : ''}
              >
                {STATUS_TEXT[check.status] ?? check.status}
                {check.required && check.status !== 'ok' ? ' · required' : ''}
              </Tag>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
