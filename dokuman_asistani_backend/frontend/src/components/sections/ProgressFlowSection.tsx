import { SectionShell } from '../layout/SectionShell';
import { progressSteps } from '../../data/mockDashboard';

function circleClass(status: 'done' | 'active' | 'next') {
  if (status === 'done') {
    return 'bg-slate-900 text-white border-slate-900';
  }
  if (status === 'active') {
    return 'bg-teal-600 text-white border-teal-600';
  }
  return 'bg-white text-slate-500 border-slate-200';
}

export function ProgressFlowSection() {
  return (
    <SectionShell
      id="progress-flow"
      eyebrow="Ok / Yuvarlak İlerleme"
      title="Orantılı küçülen daireler ve bağlayıcı çizgilerle akış görünümü"
      description="Küçük ekranlarda dikey akışa döner, daha geniş alanlarda yatay zincire geçer. Böylece taşma yerine düzenli kırılım elde edilir."
    >
      <div className="rounded-[26px] border border-slate-200 bg-slate-50/90 p-5">
        <div className="flex flex-col">
          {progressSteps.map((step, index) => {
            const isLast = index === progressSteps.length - 1;
            return (
              <div key={step.title} className="flex flex-col sm:flex-row sm:items-stretch">
                <div className="flex items-start gap-4 sm:flex-1 sm:items-center">
                  <div className={`inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-full border text-sm font-semibold ${circleClass(step.status)}`}>
                    {index + 1}
                  </div>
                  <div className="rounded-[22px] bg-white px-4 py-4">
                    <p className="text-sm font-semibold text-slate-900">{step.title}</p>
                    <p className="mt-2 text-sm leading-7 text-slate-600">{step.description}</p>
                  </div>
                </div>
                {!isLast && (
                  <>
                    <div className="ml-6 h-8 w-px bg-slate-200 sm:hidden" />
                    <div className="mx-4 hidden h-px flex-1 self-center bg-slate-200 sm:block" />
                  </>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </SectionShell>
  );
}
