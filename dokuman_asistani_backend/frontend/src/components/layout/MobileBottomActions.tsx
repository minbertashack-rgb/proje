import type { QuickAction } from '../../data/mockDashboard';

type MobileBottomActionsProps = {
  quickActions: QuickAction[];
  activeActionId: QuickAction['id'];
  onActionSelect: (id: QuickAction['id']) => void;
};

export function MobileBottomActions({
  quickActions,
  activeActionId,
  onActionSelect,
}: MobileBottomActionsProps) {
  return (
    <div className="fixed inset-x-0 bottom-3 z-40 px-3 xl:hidden">
      <div className="mx-auto flex max-w-xl items-center justify-between gap-2 rounded-[28px] border border-white/60 bg-white/90 p-2 shadow-ambient backdrop-blur-xl">
        {quickActions.map((action) => {
          const active = action.id === activeActionId;
          return (
            <button
              key={action.id}
              type="button"
              onClick={() => onActionSelect(action.id)}
              className={`flex min-w-0 flex-1 flex-col items-center gap-1 rounded-[22px] px-2 py-2.5 text-center transition ${
                active ? action.toneClass : 'bg-slate-50 text-slate-600'
              }`}
            >
              <span className={`inline-flex h-8 w-8 items-center justify-center rounded-2xl text-[11px] font-bold ${action.iconClass}`}>
                {action.title.slice(0, 1)}
              </span>
              <span className="text-[11px] font-semibold leading-tight sm:text-xs">
                {action.shortLabel}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
