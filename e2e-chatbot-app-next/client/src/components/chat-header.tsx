import { useNavigate } from 'react-router-dom';

import { SidebarToggle } from '@/components/sidebar-toggle';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { useSidebar } from './ui/sidebar';
import { useSession } from '@/contexts/SessionContext';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Bell, MessageCircle, PlusIcon, HistoryIcon } from 'lucide-react';
import { useTheme } from 'next-themes';

const DEFAULT_TITLE = 'Generate check-in performance reports for airlines';

export function ChatHeader({
  pageTitle,
  showIntermediateSteps,
  onToggleIntermediateSteps,
}: {
  pageTitle?: string;
  showIntermediateSteps?: boolean;
  onToggleIntermediateSteps?: () => void;
}) {
  const navigate = useNavigate();
  const { open, setOpen } = useSidebar();
  const { session, loading } = useSession();
  const { setTheme, resolvedTheme } = useTheme();

  const displayName =
    session?.user?.preferredUsername ||
    session?.user?.name ||
    session?.user?.email ||
    'User';
  const initials = displayName.charAt(0).toUpperCase();

  const title = pageTitle ?? DEFAULT_TITLE;

  return (
    <header className="sticky top-0 z-10 flex flex-col border-b bg-background">
      {/* Row 1: hamburger + logo + bell + chat + avatar */}
      <div className="flex items-center justify-between gap-3 px-3 py-2">
        <div className="flex items-center gap-3">
          <SidebarToggle />
          <div className="flex items-center gap-1">
            <span className="font-semibold tracking-tight text-purple-600">
              AGENT FORGE
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="relative rounded-md p-1.5 hover:bg-muted"
            aria-label="Notifications"
          >
            <Bell className="h-5 w-5 text-muted-foreground" />
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-purple-600 px-1 text-[10px] font-medium text-white">
              3
            </span>
          </button>
          <button
            type="button"
            className="rounded-md p-1.5 hover:bg-muted"
            aria-label="Chat"
          >
            <MessageCircle className="h-5 w-5 text-muted-foreground" />
          </button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="flex size-8 items-center justify-center rounded-full bg-purple-600 text-sm font-medium text-white hover:opacity-90"
                data-testid="header-user-avatar"
              >
                {loading ? (
                  <span className="animate-pulse">?</span>
                ) : (
                  initials
                )}
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              side="bottom"
              align="end"
              className="w-48"
            >
              <DropdownMenuItem
                className="cursor-pointer"
                onSelect={() =>
                  setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')
                }
              >
                {`Toggle ${resolvedTheme === 'light' ? 'dark' : 'light'} mode`}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
      {/* Row 2: title + New chat + History */}
      <div className="flex items-center justify-between gap-2 border-t border-border/40 bg-background px-3 py-2">
        <h2 className="truncate font-semibold text-foreground text-base">
          {title}
        </h2>
        <div className="flex shrink-0 items-center gap-2">
          {onToggleIntermediateSteps != null && (
            <Switch
              checked={showIntermediateSteps}
              onCheckedChange={() => onToggleIntermediateSteps()}
              label="Steps"
              title="Show/hide tool steps"
            />
          )}
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => navigate('/')}
          >
            <PlusIcon className="h-4 w-4" />
            New chat
          </Button>
          <Button
            variant={open ? 'default' : 'outline'}
            size="sm"
            className="gap-1.5"
            onClick={() => setOpen(!open)}
          >
            <HistoryIcon className="h-4 w-4" />
            History
          </Button>
        </div>
      </div>
    </header>
  );
}
