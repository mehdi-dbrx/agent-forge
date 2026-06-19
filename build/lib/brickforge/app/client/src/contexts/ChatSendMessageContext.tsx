import {
  createContext,
  useCallback,
  useContext,
  useRef,
  type ReactNode,
} from 'react';

type SendMessageFn = (message: {
  role: 'user';
  parts: Array<{ type: 'text'; text: string }>;
  metadata?: { source?: string };
}) => void;

export type ShowStaffingDutyOnlyFn = (
  zone: string,
  counter: string,
  assignedById: string,
) => void;

interface ChatSendMessageContextValue {
  /** Pass sendMessage to register, or null to unregister on unmount */
  registerSendMessage: (fn: SendMessageFn | null) => void;
  /** Register callback to clear chat and show staffing duty card directly (used by Go to Task) */
  registerShowStaffingDutyOnly: (fn: ShowStaffingDutyOnlyFn | null) => void;
  sendCheckTasks: (agentId: string) => void;
  /** Clear chat, fetch NEW duty for agentId, show StaffingDutyCard directly (no user message) */
  showStaffingDutyOnly: (agentId: string) => void;
}

const ChatSendMessageContext = createContext<ChatSendMessageContextValue | null>(null);

export function ChatSendMessageProvider({ children }: { children: ReactNode }) {
  const sendMessageRef = useRef<SendMessageFn | null>(null);
  const showStaffingDutyOnlyRef = useRef<ShowStaffingDutyOnlyFn | null>(null);

  const registerSendMessage = useCallback((fn: SendMessageFn | null) => {
    sendMessageRef.current = fn;
  }, []);

  const registerShowStaffingDutyOnly = useCallback((fn: ShowStaffingDutyOnlyFn | null) => {
    showStaffingDutyOnlyRef.current = fn;
  }, []);

  const sendCheckTasks = useCallback((_agentId: string) => {
    const send = sendMessageRef.current;
    if (send) {
      send({
        role: 'user',
        parts: [{ type: 'text', text: 'What are my assigned staffing duties?' }],
      });
    }
  }, []);

  const showStaffingDutyOnly = useCallback(async (_agentId: string) => {
    // Domain-specific task notification -- no-op when no domain is loaded.
    // Domain plugins can override via registerShowStaffingDutyOnly.
    const show = showStaffingDutyOnlyRef.current;
    if (!show) return;
  }, []);

  const value: ChatSendMessageContextValue = {
    registerSendMessage,
    registerShowStaffingDutyOnly,
    sendCheckTasks,
    showStaffingDutyOnly,
  };

  return (
    <ChatSendMessageContext.Provider value={value}>
      {children}
    </ChatSendMessageContext.Provider>
  );
}

export function useChatSendMessage(): ChatSendMessageContextValue {
  const context = useContext(ChatSendMessageContext);
  if (!context) {
    throw new Error('useChatSendMessage must be used within ChatSendMessageProvider');
  }
  return context;
}

export function useOptionalChatSendMessage(): ChatSendMessageContextValue | null {
  return useContext(ChatSendMessageContext);
}
