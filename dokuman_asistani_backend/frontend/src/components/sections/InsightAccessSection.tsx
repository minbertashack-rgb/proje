import { SectionShell } from '../layout/SectionShell';
import type { QuickAction } from '../../data/mockDashboard';

type InsightAccessSectionProps = {
  quickActions: QuickAction[];
  activeActionId: QuickAction['id'];
  onActionSelect: (id: QuickAction['id']) => void;
};

export function InsightAccessSection({
  quickActions,
  activeActionId,
  onActionSelect,
}: InsightAccessSectionProps) {
  return (
    <SectionShell
      id="insight-access"
      eyebrow="Aksiyon Erişimi"
      title="Bunu Anlamadım, Kanıt, Terimler ve Zor Kısım kartları"
      description="Bu blok içerik sonunda ikinci erişim noktasıdır. Aynı aksiyonlar drawer içinde ve mobil alt sabit barda da yer alır."
    >
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {quickActions.map((action) => {
          const active = action.id === activeActionId;
          return (
            <article
              key={action.id}
              className={`rounded-[26px] border p-5 transition ${active ? action.toneClass : 'border-slate-200 bg-white'}`}
            >
              <div className="flex items-center gap-3">
                <span className={`inline-flex h-11 w-11 items-center justify-center rounded-2xl text-sm font-semibold ${action.iconClass}`}>
                  {action.title.slice(0, 1)}
                </span>
                <div>
                  <p className="font-semibold text-slate-950">{action.title}</p>
                  <p className="mt-1 text-sm text-slate-500">{action.description}</p>
                </div>
              </div>
              <p className="mt-4 text-sm leading-7 text-slate-600">{action.detail}</p>
              <button
                type="button"
                onClick={() => onActionSelect(action.id)}
                className="mt-5 w-full rounded-[20px] border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-800"
              >
                Aktif Yap
              </button>
            </article>
          );
        })}
      </div>
    </SectionShell>
  );
}
