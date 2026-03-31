import { SidebarToggle } from '@/components/sidebar-toggle';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useSession } from '@/contexts/SessionContext';
import { useTheme } from 'next-themes';
import { Sparkles } from 'lucide-react';

const CUSTOMER_NAME = 'Airport Check-in Command Center';

export function AppHeader() {
  const { session, loading } = useSession();
  const { setTheme, resolvedTheme } = useTheme();

  const displayName =
    session?.user?.preferredUsername ||
    session?.user?.name ||
    session?.user?.email ||
    'User';
  const initials = displayName.charAt(0).toUpperCase();

  return (
    <header className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b bg-background px-3 py-2">
      <div className="flex items-center gap-3">
        <SidebarToggle />
        <span className="font-semibold tracking-tight text-foreground text-base">

        </span>
      </div>
      <div className="flex flex-1 items-center justify-center px-4">
        <span className="font-bold text-muted-foreground text-lg">
          {CUSTOMER_NAME}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-purple-600 px-3 py-1.5 font-medium text-white text-sm">
          <Sparkles className="h-4 w-4" />
          Garv
        </span>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="flex size-8 items-center justify-center rounded-full bg-muted text-muted-foreground text-sm font-medium hover:bg-muted/80"
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
    </header>
  );
}
