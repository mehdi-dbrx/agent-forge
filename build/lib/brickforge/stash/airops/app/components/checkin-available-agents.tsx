import { memo } from 'react';

export type CheckinAgent = {
  agentId: string;
  name: string;
  zone: string;
  counter: string;
  status: string;
};

export type CheckinAvailableAgentsProps = {
  agents: CheckinAgent[];
};

export const CheckinAvailableAgents = memo(function CheckinAvailableAgents({
  agents,
}: CheckinAvailableAgentsProps) {
  return (
    <div
      className="px-0 py-2"
      data-response-type="checkin_available_agents"
    >
      <p className="font-semibold text-foreground">
        Available Agent (nearby / low utilisation)
      </p>
      <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-foreground">
        {agents.map((a, i) => (
          <li key={i}>
            <span className="font-semibold">{a.name}</span>
            {a.zone && (
              <span className="text-foreground">
                {' '}
                – Zone {a.zone}
                {a.counter && `, counter ${a.counter}`}
                {a.status && ` — ${a.status}`}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
});
