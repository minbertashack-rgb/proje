import type { QuickAction } from '../../data/mockDashboard';
import { FeedbackPanel, StatusBadge } from '../common/StateViews';
import type { AuthSession, BackendHealth, DocumentPart, UploadedDocument } from '../../types/api';
import type { LoadableState } from '../../types/ui';

type RightRailProps = {
  activeAction: QuickAction;
  quickActions: QuickAction[];
  onActionSelect: (id: QuickAction['id']) => void;
  backendState: LoadableState<BackendHealth>;
  session: AuthSession | null;
  currentDocument: UploadedDocument | null;
  selectedPart: DocumentPart | null;
  liveSectionCount: number;
  mockSectionCount: number;
};

export function RightRail({
  activeAction,
  quickActions,
  onActionSelect,
  backendState,
  session,
  currentDocument,
  selectedPart,
  liveSectionCount,
  mockSectionCount,
}: RightRailProps) {
  const visibleDocument = session ? currentDocument : null;
  const visiblePart = session ? selectedPart : null;

  return (
    <div className="sticky top-20 space-y-4">
      <aside className={`section-card p-5 ${activeAction.toneClass}`}>
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">Aktif Aksiyon</p>
        <h3 className="display-font mt-2 text-xl font-semibold text-slate-950">{activeAction.title}</h3>
        <p className="mt-3 text-sm leading-7 text-slate-700">{activeAction.detail}</p>
        <ul className="mt-4 space-y-2 text-sm text-slate-700">
          {activeAction.bullets.map((bullet) => (
            <li key={bullet} className="rounded-2xl bg-white/75 px-3 py-2">
              {bullet}
            </li>
          ))}
        </ul>
      </aside>

      <aside className="section-card p-4">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Hızlı Geçiş</p>
        <div className="mt-4 space-y-2">
          {quickActions.map((action) => (
            <button
              key={action.id}
              type="button"
              onClick={() => onActionSelect(action.id)}
              className="flex w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-left transition hover:border-slate-300"
            >
              <span className="font-medium text-slate-800">{action.title}</span>
              <span className="text-xs text-slate-400">{action.shortLabel}</span>
            </button>
          ))}
        </div>
      </aside>

      <aside className="section-card p-4">
        <div className="flex items-start justify-between gap-3">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Canlı Durum</p>
          <StatusBadge
            label={session ? 'Oturum açık' : 'Misafir'}
            tone={session ? 'success' : 'warning'}
          />
        </div>
        <div className="mt-4 grid gap-3">
          <div className="surface-muted p-4">
            <p className="text-sm text-slate-500">Sistem</p>
            <p className="mt-1 text-base font-semibold text-slate-950">
              {backendState.status === 'success' ? 'Hazır' : backendState.status === 'error' ? 'Kontrol gerekli' : 'Kontrol ediliyor'}
            </p>
          </div>
          <div className="surface-muted p-4">
            <p className="text-sm text-slate-500">Aktif doküman</p>
            <p className="mt-1 text-base font-semibold text-slate-950">
              {visibleDocument?.title || 'Yok'}
            </p>
          </div>
          <div className="surface-muted p-4">
            <p className="text-sm text-slate-500">Seçili parça</p>
            <p className="mt-1 text-base font-semibold text-slate-950">
              {visiblePart?.title || 'Yok'}
            </p>
          </div>
          <div className="surface-muted p-4">
            <p className="text-sm text-slate-500">Canlı / Demo</p>
            <p className="mt-1 text-base font-semibold text-slate-950">
              {liveSectionCount} canlı, {mockSectionCount} demo
            </p>
          </div>
        </div>

        {!session ? (
          <FeedbackPanel
            title="Login gerekli"
            message="Belge yükleme ve yanıt akışları için önce giriş yapmalısın."
            tone="warning"
            className="mt-4"
          />
        ) : null}
      </aside>
    </div>
  );
}
