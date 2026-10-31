import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { listTickets } from "../lib/api";
import type { TicketSummary } from "../types";

interface WorkspaceValue {
  tickets: TicketSummary[];
  totalCount: number;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceValue | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [tickets, setTickets] = useState<TicketSummary[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const refreshInFlight = useRef<Promise<void> | null>(null);
  const refresh = useCallback(() => {
    if (refreshInFlight.current) return refreshInFlight.current;
    const request = (async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await listTickets({ limit: 100 });
        setTickets(response.items);
        setTotalCount(response.count);
      } catch (reason) {
        setError(
          reason instanceof Error ? reason.message : "Не удалось загрузить обращения.",
        );
      } finally {
        setLoading(false);
        refreshInFlight.current = null;
      }
    })();
    refreshInFlight.current = request;
    return request;
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo(
    () => ({ tickets, totalCount, loading, error, refresh }),
    [tickets, totalCount, loading, error, refresh],
  );

  return (
    <WorkspaceContext.Provider value={value}>
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error("useWorkspace must be used inside WorkspaceProvider");
  }
  return context;
}
