import { useEffect } from 'react';
import type { NavItem } from '../../constants/navigation';
import type { QuickAction } from '../../data/mockDashboard';

type DrawerProps = {
  open: boolean;
  navItems: NavItem[];
  quickActions: QuickAction[];
  activeActionId: QuickAction['id'];
  onClose: () => void;
  onActionSelect: (id: QuickAction['id']) => void;
};

export function Drawer({
  open,
  navItems,
  quickActions,
  activeActionId,
  onClose,
  onActionSelect,
}: DrawerProps) {
  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  return (
    <div
      className={`fixed inset-0 z-50 transition ${
        open ? 'pointer-events-auto bg-slate-950/35' : 'pointer-events-none bg-transparent'
      }`}
      onClick={onClose}
      aria-hidden={!open}
    >
      <aside
        className={`absolute left-0 top-0 h-full w-[86%] max-w-sm overflow-y-auto bg-white p-5 shadow-ambient transition-transform duration-300 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-6 flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Drawer</p>
            <h2 className="display-font text-xl font-semibold text-slate-950">DocVerse Menü</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-slate-200 bg-slate-50 text-slate-700"
            aria-label="Menüyü kapat"
          >
            ×
          </button>
        </div>

        <div className="space-y-3">
          <div className="surface-muted p-4">
            <p className="text-sm font-semibold text-slate-900">Sol alan mobilde drawer içine taşındı.</p>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Header sade kaldı; menü, section linkleri ve hızlı erişim kartları burada toplandı.
            </p>
          </div>

          <div className="space-y-2">
            {navItems.map((item) => (
              <a
                key={item.href}
                href={item.href}
                onClick={onClose}
                className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700"
              >
                <span>{item.label}</span>
                <span className="text-xs text-slate-400">{item.hint}</span>
              </a>
            ))}
          </div>

          <div className="pt-4">
            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Aksiyonlar</p>
            <div className="grid gap-3">
              {quickActions.map((action) => {
                const active = action.id === activeActionId;
                return (
                  <button
                    key={action.id}
                    type="button"
                    onClick={() => onActionSelect(action.id)}
                    className={`rounded-[22px] border px-4 py-4 text-left transition ${
                      active
                        ? `${action.toneClass} shadow-soft`
                        : 'border-slate-200 bg-white hover:border-slate-300'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <span className={`inline-flex h-10 w-10 items-center justify-center rounded-2xl text-sm font-semibold ${action.iconClass}`}>
                        {action.title.slice(0, 1)}
                      </span>
                      <div>
                        <p className="font-semibold text-slate-950">{action.title}</p>
                        <p className="mt-1 text-sm text-slate-600">{action.description}</p>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </aside>
    </div>
  );
}
