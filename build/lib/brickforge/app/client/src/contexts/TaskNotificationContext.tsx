import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

interface TaskNotificationContextValue {
  /** True when Agent has received a task_created event and not yet acknowledged. */
  hasUnreadTask: boolean;
  /** Call when task_created is received. */
  setUnread: () => void;
  /** Call when user acknowledges (e.g. clicks "Go to Task"). */
  clearUnread: () => void;
}

const TaskNotificationContext = createContext<TaskNotificationContextValue | null>(null);

export function TaskNotificationProvider({ children }: { children: ReactNode }) {
  const [hasUnreadTask, setHasUnreadTask] = useState(false);

  const setUnread = useCallback(() => {
    setHasUnreadTask(true);
  }, []);

  const clearUnread = useCallback(() => {
    setHasUnreadTask(false);
  }, []);

  const value = useMemo(
    () => ({ hasUnreadTask, setUnread, clearUnread }),
    [hasUnreadTask, setUnread, clearUnread],
  );

  return (
    <TaskNotificationContext.Provider value={value}>
      {children}
    </TaskNotificationContext.Provider>
  );
}

export function useTaskNotification(): TaskNotificationContextValue {
  const context = useContext(TaskNotificationContext);
  if (!context) {
    throw new Error('useTaskNotification must be used within TaskNotificationProvider');
  }
  return context;
}
