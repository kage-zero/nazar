import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from 'react';

const cx = (...parts: (string | false | undefined)[]) => parts.filter(Boolean).join(' ');

export function Card({
  inverted = false,
  className,
  ...props
}: HTMLAttributes<HTMLElement> & { inverted?: boolean }) {
  return (
    <section
      className={cx(
        'rounded-card p-6',
        inverted ? 'inverted bg-carbon text-paper' : 'bg-paper text-carbon',
        className,
      )}
      {...props}
    />
  );
}

export function Tag({
  tone = 'mint',
  children,
  className,
}: {
  tone?: 'mint' | 'mist' | 'carbon';
  children: ReactNode;
  className?: string;
}) {
  const tones = {
    mint: 'bg-mint text-carbon',
    mist: 'bg-mist text-slate',
    carbon: 'bg-carbon text-paper',
  };
  return (
    <span
      className={cx(
        'mono-label inline-flex items-center gap-2 rounded-tag px-3 py-1',
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'filled' | 'ghost' | 'ghost-inverted';
};

export function Button({ variant = 'filled', className, type = 'button', ...props }: ButtonProps) {
  const variants = {
    filled: 'rounded-button bg-carbon px-6 py-4 text-paper hover:bg-graphite',
    ghost: 'rounded-button-sm border-[1.5px] border-slate px-4 py-3 text-slate hover:bg-mist',
    'ghost-inverted':
      'rounded-button-sm border-[1.5px] border-smoke px-4 py-2 text-paper hover:bg-graphite',
  };
  return (
    <button
      type={type}
      className={cx(
        'text-base font-medium transition-colors disabled:cursor-not-allowed disabled:border-ash disabled:bg-ash disabled:text-slate',
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
