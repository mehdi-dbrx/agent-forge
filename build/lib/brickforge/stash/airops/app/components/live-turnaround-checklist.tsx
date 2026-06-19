import { memo } from 'react';
import { cn } from '@/lib/utils';

export type TaskItem = { name: string; status: string };

export type LiveTurnaroundChecklistCardProps = {
  flight: string;
  tasks: TaskItem[];
  readiness: string;
};

const READINESS_COLOURS: Record<string, string> = {
  GREEN:
    'bg-green-500 text-green-900 dark:bg-green-600 dark:text-green-100',
  AMBER:
    'bg-amber-500 text-amber-900 dark:bg-amber-600 dark:text-amber-100',
  RED: 'bg-red-500 text-red-900 dark:bg-red-600 dark:text-red-100',
};

function LiveIcon() {
  return (
    <span className="flex size-5 shrink-0 items-center justify-center text-green-600 dark:text-green-400" aria-hidden>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2 2" className="size-full">
        <circle cx="12" cy="12" r="10" />
        <circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" />
      </svg>
    </span>
  );
}

const TASK_STATUS_STYLES: Record<
  string,
  { row: string; icon: string; badge: string }
> = {
  notified: {
    row: 'border-amber-700/70 bg-amber-50 dark:border-amber-600/60 dark:bg-amber-900/25',
    icon: 'text-amber-700 dark:text-amber-500',
    badge:
      'border-amber-600/80 bg-amber-100 text-amber-900 dark:border-amber-500/60 dark:bg-amber-900/40 dark:text-amber-100',
  },
  pending: {
    row: 'border-slate-300 bg-slate-100 dark:border-slate-600 dark:bg-slate-800/60',
    icon: 'text-slate-500 dark:text-slate-400',
    badge:
      'border-slate-400 bg-slate-200 text-slate-800 dark:border-slate-500 dark:bg-slate-700 dark:text-slate-200',
  },
  'in progress': {
    row: 'border-sky-400/70 bg-sky-50 dark:border-sky-500/60 dark:bg-sky-900/25',
    icon: 'text-sky-600 dark:text-sky-400',
    badge:
      'border-sky-500/80 bg-sky-100 text-sky-900 dark:border-sky-400/60 dark:bg-sky-900/40 dark:text-sky-100',
  },
  completed: {
    row: 'border-emerald-600/70 bg-emerald-50 dark:border-emerald-500/60 dark:bg-emerald-900/25',
    icon: 'text-emerald-600 dark:text-emerald-400',
    badge:
      'border-emerald-600/80 bg-emerald-100 text-emerald-900 dark:border-emerald-500/60 dark:bg-emerald-900/40 dark:text-emerald-100',
  },
};

function TaskRow({ name, status }: TaskItem) {
  const statusKey = status.toLowerCase().trim();
  const style =
    TASK_STATUS_STYLES[statusKey] ?? TASK_STATUS_STYLES.pending;
  const isNotified = statusKey === 'notified';
  const isCompleted = statusKey === 'completed';
  const isInProgress = statusKey === 'in progress';

  return (
    <div
      className={cn(
        'flex items-center justify-between gap-2 rounded-md border px-3 py-2',
        style.row,
      )}
    >
      <span className="flex items-center gap-2 text-sm font-medium text-foreground">
        {isNotified ? (
          <span className={cn('size-4 shrink-0', style.icon)} aria-hidden title="Notified">
            <svg viewBox="0 0 24 24" fill="currentColor" className="size-4"><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm.5-13H11v6l5.2 3.2.8-1.3-4.5-2.7V7z"/></svg>
          </span>
        ) : isCompleted ? (
          <span className={cn('size-4 shrink-0', style.icon)} aria-hidden title="Completed">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="size-4"><path d="M20 6L9 17l-5-5"/></svg>
          </span>
        ) : isInProgress ? (
          <span className={cn('size-4 shrink-0', style.icon)} aria-hidden title="In Progress">
            <svg viewBox="0 0 24 24" fill="currentColor" className="size-4"><circle cx="12" cy="12" r="10"/><path fill="white" d="M12 6v6l4 2"/></svg>
          </span>
        ) : (
          <span className={cn('size-4 shrink-0', style.icon)} aria-hidden title="Pending">
            <span className="flex size-4 items-center justify-center rounded-full border border-current text-[10px] font-bold">!</span>
          </span>
        )}
        {name}
      </span>
      <span
        className={cn(
          'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium',
          style.badge,
        )}
      >
        {status}
      </span>
    </div>
  );
}

export const LiveTurnaroundChecklistCard = memo(
  function LiveTurnaroundChecklistCard({
    flight,
    tasks,
    readiness,
  }: LiveTurnaroundChecklistCardProps) {
    const readinessKey = readiness.toUpperCase();
    const footerClass =
      READINESS_COLOURS[readinessKey] ??
      'bg-slate-400 text-slate-900 dark:bg-slate-600 dark:text-slate-100';

    return (
      <div
        className="overflow-hidden rounded-xl border border-blue-200 bg-white shadow-sm dark:border-blue-900/50 dark:bg-slate-900/50"
        data-response-type="live_turnaround_checklist"
      >
        <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3 dark:border-slate-700">
          <LiveIcon />
          <p className="font-bold text-blue-600 dark:text-blue-400">
            Turnaround - {flight}
          </p>
        </div>
        <div className="border-b border-slate-200 px-3 py-2 dark:border-slate-700">
          <p className="text-xs font-medium text-muted-foreground">
            Live Turnaround Checklist (synced with TMS)
          </p>
        </div>
        <div className="flex flex-col gap-2 px-4 py-3">
          {tasks.map((task, i) => (
            <TaskRow key={`${task.name}-${i}`} name={task.name} status={task.status} />
          ))}
        </div>
        <div
          className={cn(
            'px-4 py-2.5 text-center text-sm font-semibold',
            footerClass,
          )}
        >
          Readiness vs TOBT: {readiness}
        </div>
      </div>
    );
  },
);
