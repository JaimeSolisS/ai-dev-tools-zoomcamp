import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { User } from "../types";
import * as api from "../api/client";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<User>;
  setup: (input: { username: string; display_name: string; password: string }) => Promise<User>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  setUser: (user: User) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const current = await api.me();
    setUserState(current);
  }, []);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    const { user: loggedIn } = await api.login(username, password);
    setUserState(loggedIn);
    return loggedIn;
  }, []);

  const setup = useCallback(async (input: { username: string; display_name: string; password: string }) => {
    const { user: created } = await api.setup(input);
    setUserState(created);
    return created;
  }, []);

  const logout = useCallback(async () => {
    await api.logout();
    setUserState(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, setup, logout, refresh, setUser: setUserState }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
