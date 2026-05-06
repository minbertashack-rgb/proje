import { SectionShell } from '../layout/SectionShell';
import { noteStreams } from '../../data/mockDashboard';

export function NotesSection() {
  return (
    <SectionShell
      id="notes"
      eyebrow="Akıllı Notlar / Portal Notlar"
      title="Genişte yan yana, dar görünümde yatay akışa dönen not kartları"
      description="Mobil görünümde kartlar yatay kaydırmalı çalışır; geniş ekranda aynı veriler iki kolonlu daha sakin bir ritme geçer."
    >
      <div className="flex snap-x snap-mandatory gap-4 overflow-x-auto pb-2 lg:grid lg:grid-cols-2 lg:overflow-visible">
        {noteStreams.map((stream) => (
          <article
            key={stream.title}
            className={`min-w-[280px] snap-start rounded-[26px] border p-5 ${stream.toneClass} lg:min-w-0`}
          >
            <div className="mb-5">
              <p className="text-sm font-semibold text-slate-900">{stream.title}</p>
              <p className="mt-2 text-sm leading-7 text-slate-600">{stream.subtitle}</p>
            </div>

            <div className="space-y-3">
              {stream.items.map((item) => (
                <div key={item.title} className="rounded-[22px] border border-slate-200 bg-slate-50/80 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-slate-900">{item.title}</p>
                    <span className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">{item.meta}</span>
                  </div>
                  <p className="mt-3 text-sm leading-7 text-slate-600">{item.body}</p>
                </div>
              ))}
            </div>
          </article>
        ))}
      </div>
    </SectionShell>
  );
}
