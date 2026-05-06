import type { NavItem } from '../../constants/navigation';
import { StatusBadge } from '../common/StateViews';
import type { BackendHealth, UploadedDocument } from '../../types/api';
import type { LoadableState } from '../../types/ui';

type SidebarProps = {
  navItems: NavItem[];
  currentDocument: UploadedDocument | null;
  partsCount: number;
  isAuthenticated: boolean;
  backendState: LoadableState<BackendHealth>;
  liveSectionCount: number;
  mockSectionCount: number;
};

export function Sidebar({
  navItems,
  currentDocument,
  partsCount,
  isAuthenticated,
  backendState,
  liveSectionCount,
  mockSectionCount,
}: SidebarProps) {
  const visibleDocument = isAuthenticated ? currentDocument : null;

  return (
    <div className="sticky top-20 space-y-4">
      <aside className="section-card p-4">
        <div className="mb-4 space-y-1">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Çalışma</p>
          <h2 className="display-font text-base font-semibold text-slate-950">Akış Haritası</h2>
        </div>

        <nav className="space-y-2">
          {navItems.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className="flex items-center justify-between rounded-xl border border-transparent bg-slate-50/90 px-3 py-2.5 text-sm font-medium text-slate-700 transition-colors hover:border-slate-200 hover:bg-white hover:text-slate-950"
            >
              <span>{item.label}</span>
              <span className="text-xs text-slate-400">{item.hint}</span>
            </a>
          ))}
        </nav>
      </aside>

      <aside className="section-card p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Doküman</p>
            <h3 className="display-font text-base font-semibold text-slate-950">
              {visibleDocument?.title || 'Henüz doküman yok'}
            </h3>
          </div>
          <StatusBadge
            label={backendState.status === 'success' ? 'Hazır' : backendState.status === 'error' ? 'Kontrol' : 'Bekleniyor'}
            tone={backendState.status === 'success' ? 'success' : backendState.status === 'error' ? 'error' : 'info'}
          />
        </div>

        <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <div className="mb-3 flex items-center justify-between text-sm text-slate-500">
            <span>{isAuthenticated ? 'Oturum aktif' : 'Login gerekli'}</span>
            <span className="font-semibold text-slate-900">{visibleDocument ? partsCount : 0} parça</span>
          </div>
          <div className="h-2 rounded-full bg-slate-200">
            <div
              className="h-full rounded-full bg-slate-900"
              style={{ width: `${visibleDocument ? Math.min(100, 20 + partsCount * 8) : 0}%` }}
            />
          </div>
          <ul className="mt-4 space-y-3 text-sm text-slate-600">
            <li>{visibleDocument ? visibleDocument.fileName : 'Yüklenmiş dosya bekleniyor'}</li>
            <li>{backendState.status === 'success' ? 'Sistem hazır' : backendState.status === 'error' ? 'Bağlantı kontrol edilmeli' : 'Durum kontrol ediliyor'}</li>
            <li>{isAuthenticated ? 'Hesap doğrulandı' : 'Oturum bekleniyor'}</li>
            <li>{liveSectionCount} canlı akış / {mockSectionCount} demo section</li>
          </ul>
        </div>
      </aside>
    </div>
  );
}
