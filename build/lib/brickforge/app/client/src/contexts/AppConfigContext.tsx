import { createContext, useCallback, useContext, type ReactNode } from 'react';
import useSWR from 'swr';
import { fetcher } from '@/lib/utils';

interface ConfigResponse {
  features: {
    chatHistory: boolean;
    [key: string]: boolean;
  };
  logoUrl?: string | null;
  appTitle?: string;
  dashboardTables?: string[];
}

interface AppConfigContextType {
  config: ConfigResponse | undefined;
  isLoading: boolean;
  error: Error | undefined;
  chatHistoryEnabled: boolean;
  /** Check if a dynamic feature toggle is enabled (defaults to false until config loads). */
  featureEnabled: (name: string) => boolean;
  /** Custom logo URL configured via setup panel (null until loaded). */
  logoUrl: string | null;
  /** Human-friendly app title derived from DBX_APP_NAME. */
  appTitle: string;
  /** Table names for the dashboard (from PROJECT_TABLES). */
  dashboardTables: string[];
}

const AppConfigContext = createContext<AppConfigContextType | undefined>(
  undefined,
);

export function AppConfigProvider({ children }: { children: ReactNode }) {
  const { data, error, isLoading } = useSWR<ConfigResponse>(
    '/api/config',
    fetcher,
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      // Config should be loaded once and cached
      dedupingInterval: 60000, // 1 minute
    },
  );

  const featureEnabled = useCallback(
    (name: string) => data?.features[name] ?? false,
    [data],
  );

  const value: AppConfigContextType = {
    config: data,
    isLoading,
    error,
    // Default to true until loaded to avoid breaking existing behavior
    chatHistoryEnabled: data?.features.chatHistory ?? true,
    featureEnabled,
    logoUrl: data?.logoUrl ?? null,
    appTitle: data?.appTitle ?? 'Agent Forge',
    dashboardTables: data?.dashboardTables ?? [],
  };

  return (
    <AppConfigContext.Provider value={value}>
      {children}
    </AppConfigContext.Provider>
  );
}

export function useAppConfig() {
  const context = useContext(AppConfigContext);
  if (context === undefined) {
    throw new Error('useAppConfig must be used within an AppConfigProvider');
  }
  return context;
}
