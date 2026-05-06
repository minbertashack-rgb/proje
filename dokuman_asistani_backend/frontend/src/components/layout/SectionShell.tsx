import type { ReactNode } from 'react';

type SectionShellProps = {
  id: string;
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
  aside?: ReactNode;
  className?: string;
};

export function SectionShell({
  id,
  eyebrow,
  title,
  description,
  children,
  aside,
  className = '',
}: SectionShellProps) {
  return (
    <section id={id} className={`section-card p-5 sm:p-7 ${className}`}>
      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-2">
          <span className="chip bg-slate-50">{eyebrow}</span>
          <div className="space-y-2">
            <h2 className="display-font text-2xl font-semibold tracking-tight text-slate-950 sm:text-[1.9rem]">
              {title}
            </h2>
            <p className="max-w-3xl text-sm leading-7 text-slate-600 sm:text-base">
              {description}
            </p>
          </div>
        </div>
        {aside}
      </div>
      {children}
    </section>
  );
}
