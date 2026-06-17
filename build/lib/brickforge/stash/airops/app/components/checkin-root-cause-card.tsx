import { memo } from 'react';

export type CheckinRootCauseCardProps = {
  zone: string;
  items: string[];
};

const BOLD_LABELS = ['Staffing state:', 'Border officers:', 'e-Gates:', 'Likely driver:'];

function formatRootCauseItem(item: string) {
  const lower = item.toLowerCase();
  for (const label of BOLD_LABELS) {
    if (lower.startsWith(label.toLowerCase())) {
      const rest = item.slice(label.length).trimStart();
      return (
        <>
          <span className="font-semibold">{label}</span>
          {rest ? ` ${rest}` : ''}
        </>
      );
    }
  }
  return item;
}

export const CheckinRootCauseCard = memo(function CheckinRootCauseCard({
  zone,
  items,
}: CheckinRootCauseCardProps) {
  return (
    <div
      className="rounded-lg border-2 border-red-500 bg-red-50 px-4 py-3 dark:border-red-500 dark:bg-red-950/30"
      data-response-type="checkin_root_cause"
    >
      <p className="font-semibold text-foreground">Root Cause</p>
      <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-foreground">
        {items.map((item, i) => (
          <li key={i}>{formatRootCauseItem(item)}</li>
        ))}
      </ul>
    </div>
  );
});
