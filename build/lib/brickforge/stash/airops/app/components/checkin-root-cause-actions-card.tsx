import { memo, useState, useCallback } from 'react';
import { Switch } from '@/components/ui/switch';
import runningManIcon from '@/assets/icons/running-man.png';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export type CheckinRootCauseAgent = {
  agentId: string;
  name: string;
  zone: string;
  counter: string;
  status: string;
};

export type CheckinRootCauseAction = {
  actionId: string;
  question: string;
};

export type CheckinRootCauseActionsCardProps = {
  agents: CheckinRootCauseAgent[];
  actions: CheckinRootCauseAction[];
  onConfirm: (selectedActionIds: string[]) => void;
  disabled?: boolean;
};

export const CheckinRootCauseActionsCard = memo(
  function CheckinRootCauseActionsCard({
    agents,
    actions,
    onConfirm,
    disabled = false,
  }: CheckinRootCauseActionsCardProps) {
    const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());

    const toggleAction = useCallback((index: number, checked: boolean) => {
      setSelectedIndices((prev) => {
        const next = new Set(prev);
        if (checked) next.add(index);
        else next.delete(index);
        return next;
      });
    }, []);

    const handleConfirm = useCallback(() => {
      const ids = [...selectedIndices]
        .sort((a, b) => a - b)
        .map((i) => actions[i].actionId);
      if (ids.length > 0) {
        onConfirm(ids);
      }
    }, [selectedIndices, actions, onConfirm]);

    return (
      <div
        className="rounded-xl border border-border bg-card px-4 py-3 shadow-sm"
        data-response-type="checkin_root_cause_actions"
      >
        {agents.length > 0 && (
          <div className="mb-4">
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
        )}

        {actions.length > 0 && (
          <div className="mb-4">
            <p className="mb-2 font-semibold text-foreground text-sm">
              Do you want me to
            </p>
            <div className="overflow-hidden rounded-xl border border-border">
              {actions.map((action, i) => {
                const isSelected = selectedIndices.has(i);
                return (
                  <div
                    key={i}
                    className={cn(
                      'flex items-center justify-between gap-3 border-b border-border px-3 py-2.5 last:border-b-0 transition-colors',
                      isSelected
                        ? 'bg-green-50 text-green-800 dark:bg-green-950/30 dark:text-green-300'
                        : 'text-muted-foreground',
                    )}
                  >
                    <span className="text-sm">{action.question}</span>
                    <Switch
                      checked={isSelected}
                      onCheckedChange={(checked) => toggleAction(i, checked)}
                      disabled={disabled}
                    />
                  </div>
                );
              })}
            </div>
            <div className="mt-3 flex justify-end">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8 bg-transparent hover:bg-accent/50"
                onClick={handleConfirm}
                disabled={disabled || selectedIndices.size === 0}
                title="Execute selected"
              >
                <img
                  src={runningManIcon}
                  alt="Execute"
                  className="size-8 object-contain [filter:brightness(0)_saturate(100%)_invert(27%)_sepia(51%)_saturate(2878%)_hue-rotate(230deg)]"
                />
              </Button>
            </div>
          </div>
        )}
      </div>
    );
  },
);
