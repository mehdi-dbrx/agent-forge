import { memo } from 'react';

export type CheckinRecommendedActionCardProps = {
  items: string[];
};

export const CheckinRecommendedActionCard = memo(
  function CheckinRecommendedActionCard({ items }: CheckinRecommendedActionCardProps) {
    return (
      <div
        className="rounded-lg border-2 border-blue-500 bg-blue-50 px-4 py-3 dark:border-blue-400 dark:bg-blue-950/40"
        data-response-type="checkin_recommended_action"
      >
        <p className="font-semibold text-foreground">Recommended Action</p>
        <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-foreground">
          {items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      </div>
    );
  },
);
