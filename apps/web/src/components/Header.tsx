import type { UserPublic } from '@nazar/contracts';
import type { ApiStatus } from '../api/system';
import { ApiStatusBadge } from './ApiStatusBadge';
import { Button } from './ui';

const NAV = [
  { label: 'Missions', href: '#missions', enabled: true },
  { label: 'Viewer', href: '#viewer', enabled: true },
  { label: 'Reports', href: '#reports', enabled: false },
];

export function Header({
  status,
  user,
  onSignOut,
}: {
  status: ApiStatus;
  user: UserPublic | null;
  onSignOut: () => void;
}) {
  return (
    <header className="mx-auto flex min-h-24 max-w-page flex-wrap items-center justify-between gap-4 px-4 py-6 sm:px-6 lg:min-h-32">
      <a href="/" className="flex items-baseline gap-3" aria-label="NAZAR home">
        <span className="text-2xl font-semibold tracking-tight">NAZAR</span>
        <span className="mono-label hidden text-slate sm:inline">Single-pass 3D</span>
      </a>
      <nav aria-label="Primary" className="order-3 w-full sm:order-none sm:w-auto">
        <ul className="flex items-center justify-center gap-1 rounded-pill bg-paper p-1.5">
          {NAV.map((item) => (
            <li key={item.label}>
              {item.enabled ? (
                <a
                  href={item.href}
                  className="block rounded-pill px-4 py-2 text-sm font-medium text-slate hover:bg-mist hover:text-carbon"
                >
                  {item.label}
                </a>
              ) : (
                <span
                  aria-disabled="true"
                  title="Available once a reconstruction has completed"
                  className="block cursor-not-allowed rounded-pill px-4 py-2 text-sm font-medium text-smoke"
                >
                  {item.label}
                </span>
              )}
            </li>
          ))}
        </ul>
      </nav>
      <div className="flex flex-wrap items-center gap-3">
        <ApiStatusBadge status={status} />
        {user && (
          <Button variant="ghost" className="py-2" onClick={onSignOut} title={user.email}>
            Sign out
          </Button>
        )}
      </div>
    </header>
  );
}
