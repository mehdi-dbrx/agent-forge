import { memo } from 'react';
import { cn } from '@/lib/utils';

export type CheckinImpactFlight = {
  number: string;
  departureMin: string;
};

export type CheckinImpactCardProps = {
  count: string;
  flights: CheckinImpactFlight[];
};

function AmberExclamationIcon() {
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

export const CheckinImpactCard = memo(function CheckinImpactCard({
  count,
  flights,
}: CheckinImpactCardProps) {
  return (
    <div
      className="overflow-hidden rounded-xl border-2 border-blue-500 bg-white dark:border-blue-400 dark:bg-slate-900/50"
      data-response-type="checkin_impact"
    >
      <div className="border-b border-slate-200 px-4 py-3 dark:border-slate-600">
        <p className="font-semibold text-blue-600 dark:text-blue-400">
          Impact: {count} flights now at risk of delay
        </p>
      </div>
      <div className="flex flex-col gap-2 px-4 py-3">
        {flights.map((f) => (
          <div
            key={f.number}
            className={cn(
              'flex items-center justify-between gap-2 rounded-lg border px-3 py-2',
              'border-amber-300 bg-amber-50/50 dark:border-amber-600 dark:bg-amber-950/20',
            )}
          >
            <span className="flex items-center gap-2">
              <AmberExclamationIcon />
              <span className="font-semibold text-foreground">{f.number}</span>
              <span className="text-sm text-muted-foreground">
                Departure in {f.departureMin} min
              </span>
            </span>
            <span
              className={cn(
                'rounded-full border px-2.5 py-0.5 text-xs font-medium',
                'border-amber-500 bg-amber-100 text-amber-900 dark:border-amber-600 dark:bg-amber-900/40 dark:text-amber-200',
              )}
            >
              Notified
            </span>
          </div>
        ))}
      </div>
    </div>
  );
});
