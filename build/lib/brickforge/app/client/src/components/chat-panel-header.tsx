import { useState, useEffect, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { useRole } from '@/contexts/RoleContext';
import { useTableRefresh } from '@/contexts/TableRefreshContext';
import { Switch } from '@/components/ui/switch';
import {
  PlusIcon,
  HistoryIcon,
  Maximize2,
  Minimize2,
  X,
  RotateCcw,
  Bell,
} from 'lucide-react';
import { useTaskNotification } from '@/contexts/TaskNotificationContext';
import { useAppConfig } from '@/contexts/AppConfigContext';

export function ChatPanelHeader({
  showIntermediateSteps,
  onToggleIntermediateSteps,
  onNewChat,
  onHistory,
  expanded,
  onExpand,
  onClose,
  sendMessage,
}: {
  showIntermediateSteps: boolean;
  onToggleIntermediateSteps: () => void;
  onNewChat: () => void;
  onHistory: () => void;
  expanded: boolean;
  onExpand: () => void;
  onClose?: () => void;
  sendMessage?: (message: {
    role: 'user';
    parts: Array<{ type: 'text'; text: string }>;
    metadata?: { source?: string };
  }) => void;
}) {
  const { refresh } = useTableRefresh();
  const { role, setRole } = useRole();
  const { hasUnreadTask } = useTaskNotification();
  const { featureEnabled } = useAppConfig();
  const personasEnabled = featureEnabled('personas');
  const sendMessageRef = useRef(sendMessage);
  sendMessageRef.current = sendMessage;
  const [resetting, setResetting] = useState(false);

  // Send persona message to agent on mount and when user changes role
  useEffect(() => {
    if (!personasEnabled) return;
    const fn = sendMessageRef.current;
    if (!fn) return;
    const personaMessage = `Your current persona is now ${role}`;
    fn({
      role: 'user',
      parts: [{ type: 'text', text: personaMessage }],
      metadata: { source: 'system' },
    });
  }, [role, personasEnabled]);

  const resetState = async () => {
    setResetting(true);
    try {
      const res = await fetch('/api/reset-state', { method: 'POST', credentials: 'include' });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        // Refresh all dashboard tables (domain-agnostic)
        refresh('*');
      }
    } catch {
      // Reset failed - no UI feedback
    } finally {
      setResetting(false);
    }
  };

  return (
    <header className="flex shrink-0 items-center justify-between gap-2 border-b bg-background px-3 py-2 min-h-[44px]">
      <div className="flex min-w-0 items-center gap-3">
        <span className="truncate font-semibold tracking-tight text-purple-600 text-sm">
          BrickForge
        </span>
        {personasEnabled && (
          <div className="flex items-center gap-2">
            <select
              value={role}
              onChange={(e) => {
                const newRole = e.target.value as 'Agent' | 'Manager';
                if (newRole !== role) {
                  onNewChat();
                  setRole(newRole);
                }
              }}
              className="rounded-md border border-input bg-background px-2 py-1 text-muted-foreground text-xs focus:outline-none focus:ring-2 focus:ring-ring"
              aria-label="Role"
            >
              <option value="Agent">Agent</option>
              <option value="Manager">Manager</option>
            </select>
            {role === 'Agent' && hasUnreadTask && (
              <span
                className="flex items-center justify-center rounded-full bg-blue-600 p-1.5 text-white"
                title="New staffing duty assigned"
              >
                <Bell className="h-4 w-4" />
              </span>
            )}
          </div>
        )}
      </div>
      <div className="flex shrink-0 flex-wrap items-center justify-end gap-1">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={resetState}
          disabled={resetting}
          aria-label="Reset state"
          title="Reset demo state"
        >
          <RotateCcw className={`h-4 w-4 ${resetting ? 'animate-spin' : ''}`} />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={onNewChat}
          aria-label="New chat"
        >
          <PlusIcon className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={onHistory}
          aria-label="History"
        >
          <HistoryIcon className="h-4 w-4" />
        </Button>
        <Switch
          checked={showIntermediateSteps}
          onCheckedChange={onToggleIntermediateSteps}
          label="Steps"
          title="Show/hide tool steps"
        />
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={onExpand}
          aria-label={expanded ? 'Tuck chat' : 'Expand chat'}
        >
          {expanded ? (
            <Minimize2 className="h-4 w-4" />
          ) : (
            <Maximize2 className="h-4 w-4" />
          )}
        </Button>
        {onClose != null && (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={onClose}
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>
    </header>
  );
}
