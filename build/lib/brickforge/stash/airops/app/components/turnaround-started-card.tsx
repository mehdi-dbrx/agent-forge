import { memo } from 'react';

export type TurnaroundStartedCardProps = {
  flight: string;
  etaMin: string;
  tobt: string;
};

export const TurnaroundStartedCard = memo(function TurnaroundStartedCard({
  flight,
  etaMin,
  tobt,
}: TurnaroundStartedCardProps) {
  return (
    <div
      className="rounded-lg border-2 border-blue-500 bg-slate-50 px-4 py-3 dark:border-blue-400 dark:bg-slate-800/60"
      data-response-type="turnaround_started"
    >
      <p className="font-semibold text-foreground">
        Turnaround started - {flight}
      </p>
      <p className="mt-1 flex gap-4 text-sm text-muted-foreground">
        <span>ETA: {etaMin} min</span>
        <span>TOBT {tobt}</span>
      </p>
    </div>
  );
});
