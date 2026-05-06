import type { ReactNode } from 'react';

type Tone = 'neutral' | 'success' | 'warning' | 'error' | 'info';

const toneClasses: Record<Tone, string> = {
  neutral: 'border-slate-200 bg-white text-slate-700',
  success: 'border-teal-200 bg-teal-50/80 text-teal-900',
  warning: 'border-amber-200 bg-amber-50/80 text-amber-900',
  error: 'border-rose-200 bg-rose-50/80 text-rose-900',
  info: 'border-sky-200 bg-sky-50/80 text-sky-900',
};

const badgeClasses: Record<Tone, string> = {
  neutral: 'border-slate-200 bg-white text-slate-700',
  success: 'border-teal-200 bg-teal-50 text-teal-800',
  warning: 'border-amber-200 bg-amber-50 text-amber-800',
  error: 'border-rose-200 bg-rose-50 text-rose-800',
  info: 'border-sky-200 bg-sky-50 text-sky-800',
};

type StatusBadgeProps = {
  label: string;
  tone?: Tone;
};

export function StatusBadge({ label, tone = 'neutral' }: StatusBadgeProps) {
  return (
    <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold ${badgeClasses[tone]}`}>
      {label}
    </span>
  );
}

type FeedbackPanelProps = {
  title: string;
  message: string;
  tone?: Tone;
  className?: string;
  children?: ReactNode;
  actions?: ReactNode;
};

export function FeedbackPanel({
  title,
  message,
  tone = 'neutral',
  className = '',
  children,
  actions,
}: FeedbackPanelProps) {
  const toneGlyph = {
    neutral: 'N',
    success: 'S',
    warning: 'W',
    error: 'E',
    info: 'I',
  }[tone];

  return (
    <div className={`rounded-[22px] border p-4 ${toneClasses[tone]} ${className}`}>
      <div className="flex items-start gap-3">
        <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl border border-current/10 bg-white/60 text-xs font-bold">
          {toneGlyph}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">{title}</p>
          <p className="mt-2 text-sm leading-7">{message}</p>
        </div>
      </div>
      {children ? <div className="mt-3">{children}</div> : null}
      {actions ? <div className="mt-3 flex flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}
