import { SectionShell } from '../layout/SectionShell';
import { challenges } from '../../data/mockDashboard';

export function ChallengesSection() {
  return (
    <SectionShell
      id="challenge-hub"
      eyebrow="Test Alanı"
      title="Test Zamanı, Vay Boss Fight, Kaçış Odası ve Speedrun"
      description="Ağır animasyon olmadan, sade kart düzeniyle çalışır. Meta alanları dar görünümde otomatik olarak alt alta akacak şekilde kuruldu."
    >
      <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-4">
        {challenges.map((challenge) => (
          <article key={challenge.title} className={`rounded-[26px] border p-5 ${challenge.toneClass}`}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-semibold text-slate-900">{challenge.title}</p>
                <p className="mt-1 text-sm text-slate-500">{challenge.subtitle}</p>
              </div>
              <span className="rounded-full border border-white/70 bg-white/75 px-3 py-1 text-xs font-semibold text-slate-700">
                {challenge.status}
              </span>
            </div>

            <p className="mt-4 text-sm leading-7 text-slate-700">{challenge.description}</p>

            <div className="mt-5 flex flex-wrap gap-2">
              {challenge.meta.map((item) => (
                <span key={item} className="rounded-full border border-white/70 bg-white/80 px-3 py-1 text-xs font-semibold text-slate-700">
                  {item}
                </span>
              ))}
            </div>

            <div className="mt-5 rounded-[22px] border border-white/70 bg-white/70 p-4 text-sm leading-7 text-slate-600">
              Görünüm sıkıştığında soru, süre, XP ve puan blokları tek sütun akışında aşağı dizilir.
            </div>
          </article>
        ))}
      </div>
    </SectionShell>
  );
}
