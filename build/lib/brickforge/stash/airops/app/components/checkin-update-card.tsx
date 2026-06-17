import { memo } from 'react';
import { CheckinFlightBadge } from './checkin-flight-badge';
import { cn } from '@/lib/utils';

export type CheckinUpdateCardProps = {
  zone: string;
  body: string;
  agent?: { name: string; zone: string };
  flights: Array<{ number: string; status: 'monitoring' | 'resolved' }>;
};

export const CheckinUpdateCard = memo(function CheckinUpdateCard({
  zone,
  body,
  agent,
  flights,
}: CheckinUpdateCardProps) {
  return (
    <div
      className="overflow-hidden rounded-xl border border-sky-200 bg-white shadow-sm dark:border-sky-800 dark:bg-slate-900/50"
      data-response-type="checkin_update"
    >
      <div className="border-l-4 border-blue-600 bg-sky-50/50 px-4 py-3 dark:border-blue-500 dark:bg-sky-950/30">
        <p className="font-semibold text-blue-600 dark:text-blue-400">
          Update - Zone {zone}
        </p>
      </div>
      <div className="px-4 py-3">
        <p className="text-sm text-foreground">{body}</p>
        {agent && (
          <div className="mt-3 flex items-center gap-2">
            <span className="font-medium text-foreground">{agent.name}</span>
            <span
              className={cn(
                'rounded-full px-2.5 py-0.5 text-xs font-medium',
                'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300',
              )}
            >
              Deployed to Zone {agent.zone}
            </span>
          </div>
        )}
        {flights.length > 0 && (
          <div className="mt-3 flex flex-col gap-2">
            {flights.map((f) => (
              <CheckinFlightBadge
                key={f.number}
                number={f.number}
                status={f.status}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
});
