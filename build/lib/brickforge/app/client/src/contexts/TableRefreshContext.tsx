import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

interface TableRefreshContextValue {
  refreshKeys: Record<string, number>;
  refresh: (tableName: string) => void;
}

const TableRefreshContext = createContext<TableRefreshContextValue | null>(null);

export function TableRefreshProvider({ children }: { children: ReactNode }) {
  const [refreshKeys, setRefreshKeys] = useState<Record<string, number>>({});

  const refresh = useCallback((tableName: string) => {
    setRefreshKeys((prev) => ({
      ...prev,
      [tableName]: (prev[tableName] ?? 0) + 1,
    }));
  }, []);

  const value = useMemo(
    () => ({ refreshKeys, refresh }),
    [refreshKeys, refresh],
  );

  return (
    <TableRefreshContext.Provider value={value}>
      {children}
    </TableRefreshContext.Provider>
  );
}

export function useTableRefresh(): TableRefreshContextValue {
  const context = useContext(TableRefreshContext);
  if (!context) {
    throw new Error('useTableRefresh must be used within TableRefreshProvider');
  }
  return context;
}
