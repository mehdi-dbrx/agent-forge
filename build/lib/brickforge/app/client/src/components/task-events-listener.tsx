import { toast } from 'sonner';
import { useChatSendMessage } from '@/contexts/ChatSendMessageContext';
import { useRole } from '@/contexts/RoleContext';
import { useTableRefresh } from '@/contexts/TableRefreshContext';
import { useTaskNotification } from '@/contexts/TaskNotificationContext';
import { useTaskEvents } from '@/hooks/useTaskEvents';
import { TaskNotificationToast } from '@/components/task-notification-toast';

/**
 * Listens for task_created SSE events when role is Agent.
 * On event: refreshes tables, shows toast, and sets unread badge.
 */
export function TaskEventsListener() {
  const { agentId } = useRole();
  const { refresh } = useTableRefresh();
  const { showStaffingDutyOnly } = useChatSendMessage();
  const { setUnread, clearUnread } = useTaskNotification();

  useTaskEvents(
    agentId ?? null,
    (payload) => {
      setUnread();
      refresh('*');
      toast.custom(
        (id) => (
          <TaskNotificationToast
            agentName={payload.agent_name}
            managerName={payload.manager_name}
            onGoToTask={() => {
              clearUnread();
              toast.dismiss(id);
              if (agentId) {
                showStaffingDutyOnly(agentId);
                setTimeout(() => {
                  const el = document.querySelector('[data-table-panel]');
                  const scrollParent = el?.closest('.overflow-auto');
                  if (scrollParent && el) {
                    const containerRect = scrollParent.getBoundingClientRect();
                    const elRect = el.getBoundingClientRect();
                    const scrollTop =
                      scrollParent.scrollTop + (elRect.top - containerRect.top) - 16;
                    scrollParent.scrollTo({ top: Math.max(0, scrollTop), behavior: 'smooth' });
                  } else {
                    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                  }
                }, 150);
              }
            }}
          />
        ),
        { duration: Infinity },
      );
    },
  );

  return null;
}
