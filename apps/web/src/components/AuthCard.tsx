import type { UserPublic } from '@nazar/contracts';
import { useId, useState, type SyntheticEvent } from 'react';
import { ApiError } from '../api/client';
import { auth } from '../api/missions';
import { Button, Card } from './ui';

const MIN_PASSWORD = 10;

/** First-run setup (no account exists yet) or sign in. */
export function AuthCard({
  mode,
  onSignedIn,
}: {
  mode: 'setup' | 'signed-out';
  onSignedIn: (user: UserPublic) => void;
}) {
  const ids = { email: useId(), password: useId(), hint: useId() };
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const setup = mode === 'setup';

  const submit = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    if (setup && password.length < MIN_PASSWORD) {
      setError(`Use at least ${MIN_PASSWORD} characters for the password.`);
      return;
    }
    setBusy(true);
    try {
      const user = await (setup ? auth.setup : auth.login)({ email: email.trim(), password });
      onSignedIn(user);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not reach the API. Try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card id="missions" aria-labelledby="auth-heading">
      <span className="mono-label text-slate">{setup ? 'First run' : 'Operator access'}</span>
      <h2 id="auth-heading" className="heading mt-2">
        {setup ? 'Create the operator account' : 'Sign in'}
      </h2>
      <p className="mt-2 mb-6 text-slate">
        {setup
          ? 'No account exists yet. This one-time step only works from this computer; the password is stored hashed in your local database.'
          : 'Missions and uploaded videos are private to the operator account.'}
      </p>
      <form className="flex flex-col gap-4" onSubmit={(e) => void submit(e)} noValidate>
        <div className="flex flex-col gap-1">
          <label htmlFor={ids.email} className="mono-label text-slate">
            Email
          </label>
          <input
            id={ids.email}
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
            }}
            className="rounded-button-sm border-[1.5px] border-ash bg-paper px-4 py-3 focus:border-carbon"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor={ids.password} className="mono-label text-slate">
            Password
          </label>
          <input
            id={ids.password}
            type="password"
            autoComplete={setup ? 'new-password' : 'current-password'}
            required
            minLength={setup ? MIN_PASSWORD : undefined}
            aria-describedby={setup ? ids.hint : undefined}
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
            }}
            className="rounded-button-sm border-[1.5px] border-ash bg-paper px-4 py-3 focus:border-carbon"
          />
          {setup && (
            <span id={ids.hint} className="text-sm text-slate">
              At least {MIN_PASSWORD} characters.
            </span>
          )}
        </div>
        {error && (
          <p role="alert" className="rounded-button bg-carbon px-4 py-3 text-sm text-paper">
            {error}
          </p>
        )}
        <Button type="submit" disabled={busy} className="self-start">
          {busy ? 'Working…' : setup ? 'Create account' : 'Sign in'}
        </Button>
      </form>
    </Card>
  );
}
