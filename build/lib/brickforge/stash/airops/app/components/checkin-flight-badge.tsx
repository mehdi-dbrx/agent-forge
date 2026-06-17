import { memo } from 'react';
import { cn } from '@/lib/utils';

export type CheckinFlightBadgeProps = {
  number: string;
  status: 'monitoring' | 'resolved';
};

function WarningIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      className="size-5 shrink-0 text-amber-600 dark:text-amber-500"
      aria-hidden
    >
      <path d="M12 2L1 21h22L12 2zm0 3.99L19.53 19H4.47L12 5.99zM11 10v4h2v-4h-2zm0 6v2h2v-2h-2z" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      className="size-5 shrink-0 text-green-600 dark:text-green-500"
      aria-hidden
    >
      <path d="M20 6L9 17l-5-5" />
    </svg>
  );
}

export const CheckinFlightBadge = memo(function CheckinFlightBadge({
  number,
  status,
}: CheckinFlightBadgeProps) {
  const isMonitoring = status === 'monitoring';

  return (
    <div
      className={cn(
        'flex items-center justify-between gap-2 rounded-lg border px-3 py-2',
        isMonitoring
          ? 'border-amber-400 bg-white dark:border-amber-500 dark:bg-slate-900/50'
          : 'border-green-500 bg-green-50 dark:border-green-600 dark:bg-green-950/30',
      )}
      data-response-type="checkin_flight_badge"
    >
      <span className="flex items-center gap-2">
        {isMonitoring ? <WarningIcon /> : <CheckIcon />}
        <span className="font-semibold text-foreground">{number}</span>
      </span>
      <span
        className={cn(
          'rounded-full px-2.5 py-0.5 text-xs font-medium',
          isMonitoring
            ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200'
            : 'border border-green-500 bg-white text-green-700 dark:border-green-600 dark:bg-slate-900/50 dark:text-green-300',
        )}
      >
        {isMonitoring ? 'Monitoring' : 'Delay Risk Removed'}
      </span>
    </div>
  );
});
