import type { NavItem } from '../../constants/navigation';
import type { QuickAction } from '../../data/mockDashboard';
import type { AuthSession } from '../../types/api';

type HeaderProps = {
  navItems: NavItem[];
  quickActions: QuickAction[];
  activeActionId: QuickAction['id'];
  onActionSelect: (id: QuickAction['id']) => void;
  onMenuOpen: () => void;
  session: AuthSession | null;
  onAuthOpen: (mode: 'login' | 'register') => void;
  onLogout: () => void;
};

export function Header({
  navItems,
  quickActions,
  activeActionId,
  onActionSelect,
  onMenuOpen,
  session,
  onAuthOpen,
  onLogout,
}: HeaderProps) {
  const activeAction = quickActions.find((action) => action.id === activeActionId) ?? quickActions[0];
  const initials = (session?.username ?? 'DV').slice(0, 2).toUpperCase();

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/[0.92] shadow-[0_10px_30px_rgba(15,23,42,0.06)] backdrop-blur-xl">
      <div className="mx-auto max-w-[1600px] px-4 py-3 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3 xl:hidden">
          <button
            type="button"
            onClick={onMenuOpen}
            className="inline-flex h-10 w-10 flex-none items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-700 shadow-soft transition-colors hover:border-slate-300"
            aria-label="Menüyü aç"
          >
            <span className="space-y-1.5">
              <span className="block h-0.5 w-5 rounded-full bg-current" />
              <span className="block h-0.5 w-5 rounded-full bg-current" />
              <span className="block h-0.5 w-5 rounded-full bg-current" />
            </span>
          </button>
          <a href="#overview" className="flex min-w-0 flex-1 items-center gap-2">
            <span className="grid h-9 w-9 flex-none place-items-center rounded-xl bg-gradient-to-br from-teal-500 via-sky-500 to-indigo-500 text-sm font-extrabold text-white shadow-soft">
              D
            </span>
            <span className="display-font truncate text-lg font-semibold tracking-tight text-slate-950">DocVerse</span>
          </a>
          <button
            type="button"
            onClick={() => (session ? onActionSelect(activeAction.id) : onAuthOpen('login'))}
            className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-700 sm:inline-flex"
          >
            {session ? activeAction.shortLabel : 'Giriş Yap'}
          </button>
        </div>

        <div className="hidden min-w-0 items-center gap-4 xl:grid xl:grid-cols-[220px_minmax(0,1fr)_430px]">
          <a href="#overview" className="flex min-w-0 items-center gap-3">
            <span className="grid h-10 w-10 flex-none place-items-center rounded-xl bg-gradient-to-br from-teal-500 via-sky-500 to-indigo-500 text-sm font-extrabold text-white shadow-soft">
              D
            </span>
            <span className="min-w-0">
              <span className="display-font block truncate text-lg font-semibold tracking-tight text-slate-950">DocVerse</span>
              <span className="block truncate text-xs font-medium text-slate-500">Belge çalışma alanı</span>
            </span>
          </a>

          <nav className="scrollbar-subtle flex min-w-0 items-center justify-center gap-1 overflow-x-auto">
            {navItems.map((item, index) => (
              <a
                key={item.href}
                href={item.href}
                className={`nav-pill whitespace-nowrap ${index === 0 ? 'nav-pill-active' : ''}`}
              >
                {item.label}
              </a>
            ))}
          </nav>

          <div className="flex min-w-0 items-center justify-end gap-2">
            <label className="relative min-w-0 flex-1">
              <span className="pointer-events-none absolute left-3 top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full border-2 border-slate-400" />
              <input
                type="search"
                placeholder="Ara"
                className="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 pl-8 pr-3 text-sm text-slate-800 outline-none transition focus:border-teal-300 focus:bg-white"
              />
            </label>
            <button type="button" className="icon-button" aria-label="Bildirimler">
              <span className="h-2 w-2 rounded-full bg-teal-500" />
            </button>
            {session ? (
              <>
                <button
                  type="button"
                  onClick={() => onActionSelect(activeAction.id)}
                  className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-300"
                >
                  {activeAction.shortLabel}
                </button>
                <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-2 py-1.5">
                  <span className="grid h-7 w-7 place-items-center rounded-lg bg-slate-900 text-[11px] font-bold text-white">
                    {initials}
                  </span>
                  <span className="max-w-[88px] truncate text-xs font-semibold text-slate-700">
                    {session.username ?? 'Profil'}
                  </span>
                  <span className="rounded-lg bg-teal-50 px-2 py-1 text-[11px] font-bold text-teal-700">Lv 3</span>
                </div>
                <button
                  type="button"
                  onClick={onLogout}
                  className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-950"
                >
                  Çıkış
                </button>
              </>
            ) : (
              <div className="flex flex-none items-center gap-2">
                <button
                  type="button"
                  onClick={() => onAuthOpen('login')}
                  className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 transition hover:border-teal-200 hover:text-teal-800"
                >
                  Giriş Yap
                </button>
                <button
                  type="button"
                  onClick={() => onAuthOpen('register')}
                  className="rounded-xl bg-slate-900 px-3 py-2 text-sm font-semibold text-white transition hover:bg-slate-800"
                >
                  Kayıt Ol
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
