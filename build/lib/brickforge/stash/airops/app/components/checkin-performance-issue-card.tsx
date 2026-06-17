import { memo } from 'react';

export type CheckinPerformanceIssueCardProps = {
  zone: string;
  pctChange: string;
  windowMins: string;
  avgCheckin?: string;
  baseline?: string;
  timestamp?: string;
};

function ExclamationIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      className="size-5 shrink-0 text-red-600 dark:text-red-500"
      aria-hidden
    >
      <path d="M12 2L1 21h22L12 2zm0 3.99L19.53 19H4.47L12 5.99zM11 10v4h2v-4h-2zm0 6v2h2v-2h-2z" />
    </svg>
  );
}

export const CheckinPerformanceIssueCard = memo(
  function CheckinPerformanceIssueCard({
    zone,
    pctChange,
    windowMins,
    avgCheckin,
    baseline,
    timestamp,
  }: CheckinPerformanceIssueCardProps) {
    return (
      <div
        className="rounded-lg border-2 border-red-500 bg-red-50 px-4 py-3 dark:border-red-500 dark:bg-red-950/30"
        data-response-type="checkin_performance_issue"
      >
        <div className="flex items-center gap-2">
          <ExclamationIcon />
          <p className="font-semibold text-foreground">
            Check-in Performance Issue Detected
          </p>
        </div>
        <p className="mt-2 text-sm text-foreground">
          Average check-in time in <span className="font-semibold">Zone {zone}</span> has
          increased by <span className="font-semibold">{pctChange}%</span> over the last{' '}
          <span className="font-semibold">{windowMins} minutes</span>.
        </p>
        {avgCheckin && baseline && (
          <p className="mt-1 text-sm text-muted-foreground">
            Avg check-in: {avgCheckin} min (baseline {baseline} min)
            {timestamp && ` at ${timestamp}`}
          </p>
        )}
      </div>
    );
  },
);
