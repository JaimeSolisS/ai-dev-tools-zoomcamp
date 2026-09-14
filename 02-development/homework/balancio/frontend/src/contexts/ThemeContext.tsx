import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { Theme } from "../types";
import { useAuth } from "../auth/AuthContext";
import * as api from "../api/client";

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { user, setUser } = useAuth();
  const [theme, setThemeState] = useState<Theme>(() => {
    const stored = localStorage.getItem("balancio_theme");
    return stored === "dark" ? "dark" : "light";
  });

  useEffect(() => {
    if (user) setThemeState(user.theme);
  }, [user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("balancio_theme", theme);
  }, [theme]);

  const setTheme = (next: Theme) => {
    setThemeState(next);
    if (user) {
      api
        .updateMyTheme(user.id, next)
        .then(setUser)
        .catch(() => {
          /* theme preference is best-effort */
        });
    }
  };

  const toggleTheme = () => setTheme(theme === "dark" ? "light" : "dark");

  return <ThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}
