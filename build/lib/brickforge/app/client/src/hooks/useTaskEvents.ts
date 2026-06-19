import { useEffect, useRef } from 'react';

export interface TaskCreatedPayload {
  assigned_to_id: string;
  agent_name?: string;
  manager_name?: string;
}

const DEBUG_TASK_EVENTS =
  typeof window !== 'undefined' &&
  (import.meta.env?.DEV || (window as unknown as { __DEBUG_TASK_EVENTS?: boolean }).__DEBUG_TASK_EVENTS);

/**
 * Subscribe to SSE staffing/task events. When a staffing duty is created for the given assigned_to_id,
 * the onTaskCreated callback is invoked with the event payload (agent_name, manager_name).
 * Reconnects on error to handle proxy timeouts / dropped connections.
 */
export function useTaskEvents(
  assignedTo: string | null,
  onTaskCreated: (payload: TaskCreatedPayload) => void,
): void {
  const onTaskCreatedRef = useRef(onTaskCreated);
  onTaskCreatedRef.current = onTaskCreated;

  useEffect(() => {
    if (!assignedTo) return;

    const url = `/api/events/tasks?assigned_to=${encodeURIComponent(assignedTo)}`;
    let es: EventSource | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;

    function connect() {
      es = new EventSource(url);
      if (DEBUG_TASK_EVENTS) console.log('[task-events] SSE connecting', url);

      es.onopen = () => {
        if (DEBUG_TASK_EVENTS) console.log('[task-events] SSE connected');
      };

      es.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data) as {
            type?: string;
            assigned_to_id?: string;
            agent_name?: string;
            manager_name?: string;
          };
          if (data.type === 'task_created') {
            if (DEBUG_TASK_EVENTS) console.log('[task-events] task_created received', data);
            onTaskCreatedRef.current({
              assigned_to_id: data.assigned_to_id ?? assignedTo,
              agent_name: data.agent_name,
              manager_name: data.manager_name,
            });
          }
        } catch {
          // ignore parse errors
        }
      };

      es.onerror = () => {
        if (DEBUG_TASK_EVENTS) console.warn('[task-events] SSE error, reconnecting in 3s');
        es?.close();
        es = null;
        reconnectTimeout = setTimeout(connect, 3000);
      };
    }

    connect();

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      es?.close();
    };
  }, [assignedTo]);
}
