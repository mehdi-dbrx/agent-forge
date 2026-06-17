import { NavLink, useLocation } from 'react-router-dom';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar';
import { useSidebar } from '@/components/ui/sidebar';
import {
  Home,
  LayoutDashboard,
  Network,
  FileText,
  BarChart3,
  ChevronRight,
  ChevronLeft,
} from 'lucide-react';
import type { ClientSession } from '@chat-template/auth';

const navItems = [
  { to: '/', icon: Home, label: 'Home' },
  { icon: LayoutDashboard, label: 'Dashboard' },
  { icon: Network, label: 'Network' },
  { icon: FileText, label: 'Documents' },
  { icon: BarChart3, label: 'Reports' },
] as const;

export function AppSidebar({
  user: _user,
  preferredUsername: _preferredUsername,
}: {
  user: ClientSession['user'] | undefined;
  preferredUsername: string | null;
}) {
  const location = useLocation();
  const { toggleSidebar, state } = useSidebar();

  return (
    <Sidebar
      className="group-data-[side=left]:border-r-0"
      collapsible="icon"
    >
      <SidebarContent className="gap-0 px-2 pt-2">
        <SidebarMenu>
          {navItems.map((item) => {
            const Icon = item.icon;
            const isHome = item.to === '/';
            const isActive =
              isHome && location.pathname === '/'
                ? true
                : !isHome && false;
            return (
              <SidebarMenuItem key={item.label}>
                {isHome ? (
                  <SidebarMenuButton
                    asChild
                    isActive={isActive}
                    tooltip={item.label}
                  >
                    <a
                      href="/"
                      className="flex items-center gap-3 rounded-md px-2 py-2"
                    >
                      <Icon className="h-5 w-5" />
                      <span>{item.label}</span>
                    </a>
                  </SidebarMenuButton>
                ) : (
                  <SidebarMenuButton
                    tooltip={item.label}
                    className="cursor-default opacity-70"
                    disabled
                  >
                    <Icon className="h-5 w-5" />
                    <span>{item.label}</span>
                  </SidebarMenuButton>
                )}
              </SidebarMenuItem>
            );
          })}
        </SidebarMenu>
      </SidebarContent>
      <SidebarFooter className="mt-auto p-2">
        <SidebarMenuButton
          onClick={toggleSidebar}
          tooltip={state === 'collapsed' ? 'Expand sidebar' : 'Collapse sidebar'}
          className="w-full"
        >
          {state === 'collapsed' ? (
            <ChevronRight className="h-5 w-5" />
          ) : (
            <ChevronLeft className="h-5 w-5" />
          )}
          <span>{state === 'collapsed' ? 'Expand' : 'Collapse'}</span>
        </SidebarMenuButton>
      </SidebarFooter>
    </Sidebar>
  );
}
