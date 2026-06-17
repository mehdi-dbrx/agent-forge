import { Clock } from 'lucide-react';
import { memo } from 'react';

export type StaffingDutyCardProps = {
  zone: string;
  counter: string;
  assignedById: string;
  sendMessage: (message: { role: 'user'; parts: Array<{ type: 'text'; text: string }>; metadata?: { source?: string } }) => void;
};

export const StaffingDutyCard = memo(function StaffingDutyCard({
  zone,
  counter,
  assignedById: _assignedById,
  sendMessage,
}: StaffingDutyCardProps) {
  const handleArrived = () => {
    sendMessage({
      role: 'user',
      parts: [{ type: 'text', text: `Arrived at Counter ${counter}` }],
      metadata: { source: 'staffing_duty' },
    });
  };

  return (
    <div
      className="rounded-lg border-2 border-blue-500 bg-blue-50 px-4 py-3 dark:border-blue-500 dark:bg-blue-950/30"
      data-response-type="staffing_duty"
    >
      <div className="flex items-center gap-2 text-blue-700 dark:text-blue-300 font-semibold">
        <Clock className="size-4" />
        Staffing Request - Zone {zone}
      </div>
      <p className="mt-2 text-sm text-foreground">
        Please proceed to Check-in Counter {counter} immediately.
      </p>
      <p className="mt-1 text-sm text-muted-foreground">
        Tap Arrived once seated.
      </p>
      <button
        type="button"
        onClick={handleArrived}
        className="mt-3 w-full rounded-lg bg-blue-600 py-2.5 font-medium text-white hover:bg-blue-700"
      >
        Arrived at Counter {counter}
      </button>
    </div>
  );
});
