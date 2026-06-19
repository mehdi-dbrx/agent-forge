import { memo } from 'react';

export type CheckinConsequencesCardProps = {
  items: string[];
};

export const CheckinConsequencesCard = memo(function CheckinConsequencesCard({
  items,
}: CheckinConsequencesCardProps) {
  return (
    <div
      className="rounded-lg border border-slate-200 bg-slate-100 px-4 py-3 dark:border-slate-600 dark:bg-slate-800/50"
      data-response-type="checkin_consequences"
    >
      <p className="font-semibold text-foreground">If no action taken</p>
      <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-foreground">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
});
