import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

export type RoleType = 'Agent' | 'Manager';

interface RoleContextValue {
  role: RoleType;
  setRole: (role: RoleType) => void;
  /** When role is Agent, the agent ID (e.g. A10). Used for staffing events subscription. */
  agentId: string | undefined;
}

const RoleContext = createContext<RoleContextValue | null>(null);

export function RoleProvider({ children }: { children: ReactNode }) {
  const [role, setRoleState] = useState<RoleType>('Manager');

  const setRole = useCallback((r: RoleType) => {
    setRoleState(r);
  }, []);

  const agentId = role === 'Agent' ? 'A14' : undefined;
  const value = useMemo(() => ({ role, setRole, agentId }), [role, setRole, agentId]);

  return (
    <RoleContext.Provider value={value}>
      {children}
    </RoleContext.Provider>
  );
}

export function useRole(): RoleContextValue {
  const context = useContext(RoleContext);
  if (!context) {
    throw new Error('useRole must be used within RoleProvider');
  }
  return context;
}
