import { useState, useCallback } from 'react';
import { Outlet, useNavigate, useLocation, useParams } from 'react-router-dom';
import { AppHeader } from '@/components/AppHeader';
import { AppSidebar } from '@/components/app-sidebar';
import { EmbeddedChatPanel } from '@/components/embedded-chat-panel';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import { TaskEventsListener } from '@/components/task-events-listener';
import { ChatSendMessageProvider } from '@/contexts/ChatSendMessageContext';
import { RoleProvider } from '@/contexts/RoleContext';
import { TaskNotificationProvider } from '@/contexts/TaskNotificationContext';
import { useSession } from '@/contexts/SessionContext';
import { TableRefreshProvider } from '@/contexts/TableRefreshContext';
import { generateUUID } from '@/lib/utils';

export default function ChatLayout() {
  const { session, loading } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const { id: paramId } = useParams<{ id: string }>();

  const [newChatId, setNewChatId] = useState(() => generateUUID());

  // Keep sidebar tucked (icon-only) by default for the demo
  const sidebarDefaultOpen = false;

  const chatId =
    location.pathname === '/' ? newChatId : (paramId ?? newChatId);

  const onNewChat = useCallback(() => {
    setNewChatId(generateUUID());
    navigate('/');
  }, [navigate]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    );
  }

  if (!session?.user) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <h1 className="mb-4 font-bold text-2xl">Authentication Required</h1>
          <p className="text-muted-foreground">
            Please authenticate using Databricks to use this application.
          </p>
        </div>
      </div>
    );
  }

  const preferredUsername = session.user.preferredUsername ?? null;

  return (
    <SidebarProvider defaultOpen={sidebarDefaultOpen}>
      <ChatSendMessageProvider>
        <RoleProvider>
          <TaskNotificationProvider>
            <TableRefreshProvider>
              <TaskEventsListener />
            <div className="flex h-svh w-full flex-col overflow-hidden">
          <AppHeader />
          <div className="flex min-h-0 min-w-0 flex-1 w-full overflow-hidden">
            <AppSidebar
              user={session.user}
              preferredUsername={preferredUsername}
            />
            <SidebarInset className="min-h-0 min-w-0 flex-1 overflow-auto">
              <Outlet />
            </SidebarInset>
            <EmbeddedChatPanel chatId={chatId} onNewChat={onNewChat} />
          </div>
            </div>
            </TableRefreshProvider>
          </TaskNotificationProvider>
        </RoleProvider>
      </ChatSendMessageProvider>
    </SidebarProvider>
  );
}
