import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Chat } from '@/components/chat';
import { SidebarHistory } from '@/components/sidebar-history';
import {
  Sheet,
  SheetContent,
  SheetTitle,
} from '@/components/ui/sheet';
import { useSession } from '@/contexts/SessionContext';
import { useChatData } from '@/hooks/useChatData';
import { generateUUID } from '@/lib/utils';
import type { LanguageModelUsage } from 'ai';
import type { LanguageModelV3Usage } from '@ai-sdk/provider';

function fromV3Usage(
  usage: LanguageModelV3Usage | null | undefined,
): LanguageModelUsage | undefined {
  if (!usage) return undefined;
  return {
    inputTokens: usage.inputTokens?.total,
    outputTokens: usage.outputTokens?.total,
    totalTokens:
      (usage.inputTokens?.total ?? 0) + (usage.outputTokens?.total ?? 0),
    inputTokenDetails: {
      noCacheTokens: usage.inputTokens?.noCache,
      cacheReadTokens: usage.inputTokens?.cacheRead,
      cacheWriteTokens: usage.inputTokens?.cacheWrite,
    },
    outputTokenDetails: {
      textTokens: usage.outputTokens?.text,
      reasoningTokens: usage.outputTokens?.reasoning,
    },
  };
}

const CHAT_PANEL_WIDTH = 525;
const CHAT_PANEL_MIN = 360;
const CHAT_PANEL_MAX = 800;
const CHAT_PANEL_WIDTH_KEY = 'chat-panel-width';

export function EmbeddedChatPanel({
  chatId,
  onNewChat,
}: {
  chatId: string;
  onNewChat: () => void;
}) {
  const { session } = useSession();
  const location = useLocation();
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [modelId, setModelId] = useState('chat-model');
  const [panelWidth, setPanelWidth] = useState(() => {
    if (typeof window === 'undefined') return CHAT_PANEL_WIDTH;
    const saved = localStorage.getItem(CHAT_PANEL_WIDTH_KEY);
    if (saved) {
      const w = parseInt(saved, 10);
      if (!Number.isNaN(w) && w >= CHAT_PANEL_MIN && w <= CHAT_PANEL_MAX) return w;
    }
    return CHAT_PANEL_WIDTH;
  });
  const widthRef = useRef(panelWidth);
  widthRef.current = panelWidth;

  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = panelWidth;

    const onMove = (moveEvent: MouseEvent) => {
      const delta = startX - moveEvent.clientX;
      const next = Math.max(CHAT_PANEL_MIN, Math.min(CHAT_PANEL_MAX, startWidth + delta));
      setPanelWidth(next);
      widthRef.current = next;
    };

    const onUp = () => {
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      localStorage.setItem(CHAT_PANEL_WIDTH_KEY, String(widthRef.current));
    };

    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [panelWidth]);

  const isExistingChat = location.pathname.startsWith('/chat/');
  const { chatData, error } = useChatData(chatId, isExistingChat);

  useEffect(() => {
    const saved = localStorage.getItem('chat-model');
    if (saved) setModelId(saved);
  }, []);

  useEffect(() => {
    if (historyOpen && location.pathname.startsWith('/chat/')) {
      setHistoryOpen(false);
    }
  }, [historyOpen, location.pathname]);

  const handleClose = () => {
    setExpanded(false);
  };

  if (!session?.user) {
    return null;
  }

  const showLoading =
    isExistingChat && (error !== undefined || !chatData || chatData.chat.id !== chatId);
  const showError = isExistingChat && error !== undefined && !chatData;

  return (
    <>
      <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
        <SheetContent
          side="right"
          className="w-full sm:max-w-md"
          aria-describedby={undefined}
        >
          <SheetTitle className="sr-only">Chat history</SheetTitle>
          <div className="mt-4 flex flex-col gap-2 px-2">
            <h2 className="font-semibold text-foreground text-base">
              History
            </h2>
            <SidebarHistory
              user={session.user}
              searchQuery=""
            />
          </div>
        </SheetContent>
      </Sheet>

      <div
        className={expanded
          ? 'fixed inset-0 z-40 flex flex-col border-l bg-background'
          : 'relative flex h-full min-h-0 shrink-0 flex-col border-l bg-background overflow-hidden'}
        style={expanded ? undefined : { width: panelWidth }}
      >
        {!expanded && (
          <div
            role="separator"
            aria-orientation="vertical"
            aria-valuenow={panelWidth}
            tabIndex={0}
            onMouseDown={handleResizeStart}
            className="absolute left-0 top-0 z-10 h-full w-2 shrink-0 cursor-col-resize touch-none border-l border-transparent hover:border-border hover:bg-muted/50"
          />
        )}
        {showError && (
          <div className="flex flex-1 items-center justify-center p-4 text-center text-muted-foreground text-sm">
            {error}
          </div>
        )}
        {showLoading && !showError && (
          <div className="flex flex-1 items-center justify-center p-4 text-muted-foreground text-sm">
            Loading chat...
          </div>
        )}
        {!showLoading && !showError && (
          <Chat
            key={chatId}
            id={chatId}
            initialMessages={
              isExistingChat && chatData
                ? chatData.messages
                : []
            }
            initialChatModel={modelId}
            initialVisibilityType={
              isExistingChat && chatData
                ? chatData.chat.visibility
                : 'private'
            }
            isReadonly={false}
            session={session}
            initialLastContext={
              isExistingChat && chatData
                ? fromV3Usage(chatData.chat.lastContext)
                : undefined
            }
            panelHeaderProps={{
              onNewChat,
              onHistory: () => setHistoryOpen(true),
              expanded,
              onExpand: () => setExpanded((e) => !e),
              onClose: handleClose,
            }}
          />
        )}
      </div>
    </>
  );
}
