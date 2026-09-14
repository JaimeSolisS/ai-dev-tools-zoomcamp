import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { User } from "../types";
import * as api from "../api/client";
import { useAuth } from "../auth/AuthContext";

interface UsersContextValue {
  users: User[];
  loading: boolean;
  nameOf: (id: string) => string;
  userById: (id: string) => User | undefined;
  refresh: () => Promise<void>;
}

const UsersContext = createContext<UsersContextValue | null>(null);

export function UsersProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const list = await api.listUsers();
    setUsers(list);
  }, []);

  useEffect(() => {
    if (user) {
      setLoading(true);
      refresh().finally(() => setLoading(false));
    } else {
      setUsers([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, refresh]);

  const nameOf = useCallback(
    (id: string) => users.find((u) => u.id === id)?.display_name ?? "Unknown",
    [users],
  );
  const userById = useCallback((id: string) => users.find((u) => u.id === id), [users]);

  return (
    <UsersContext.Provider value={{ users, loading, nameOf, userById, refresh }}>
      {children}
    </UsersContext.Provider>
  );
}

export function useUsers(): UsersContextValue {
  const ctx = useContext(UsersContext);
  if (!ctx) throw new Error("useUsers must be used within a UsersProvider");
  return ctx;
}
