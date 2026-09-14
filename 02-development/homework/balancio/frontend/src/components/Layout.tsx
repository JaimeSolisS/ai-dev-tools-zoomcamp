import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../contexts/ThemeContext";
import { APP_NAME } from "../config";

const navItems = [
  { to: "/dashboard", label: "Dashboard", icon: "🏠" },
  { to: "/groups", label: "Groups", icon: "👥" },
  { to: "/settlements", label: "Settlements", icon: "💸" },
  { to: "/refunds", label: "Refunds", icon: "↩️" },
  { to: "/history", label: "History", icon: "🕘" },
];

function navLinkClass(isActive: boolean) {
  return `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition ${
    isActive
      ? "bg-teal-600 text-white"
      : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700"
  }`;
}

export function Layout() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur dark:border-slate-700 dark:bg-slate-800/90">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-6">
            <NavLink to="/dashboard" className="text-lg font-bold text-teal-700 dark:text-teal-400">
              {APP_NAME}
            </NavLink>
            <nav className="hidden gap-1 md:flex">
              {navItems.map((item) => (
                <NavLink key={item.to} to={item.to} className={({ isActive }) => navLinkClass(isActive)}>
                  <span aria-hidden>{item.icon}</span>
                  {item.label}
                </NavLink>
              ))}
              {user?.role === "admin" && (
                <NavLink to="/admin" className={({ isActive }) => navLinkClass(isActive)}>
                  <span aria-hidden>🛠️</span>
                  Admin
                </NavLink>
              )}
            </nav>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={toggleTheme}
              aria-label="Toggle theme"
              className="rounded-lg border border-slate-200 p-2 text-sm hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-700"
            >
              {theme === "dark" ? "☀️" : "🌙"}
            </button>
            <NavLink
              to="/profile"
              className="hidden text-sm font-medium text-slate-700 hover:underline dark:text-slate-200 sm:block"
            >
              {user?.display_name}
            </NavLink>
            <button
              onClick={handleLogout}
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              Log out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6 pb-24 md:pb-6">
        <Outlet />
      </main>

      <nav className="fixed inset-x-0 bottom-0 z-30 flex justify-around border-t border-slate-200 bg-white py-1 dark:border-slate-700 dark:bg-slate-800 md:hidden">
        {[...navItems, ...(user?.role === "admin" ? [{ to: "/admin", label: "Admin", icon: "🛠️" }] : [])].map(
          (item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex flex-col items-center gap-0.5 rounded-lg px-2 py-1.5 text-[11px] font-medium ${
                  isActive ? "text-teal-600 dark:text-teal-400" : "text-slate-500 dark:text-slate-400"
                }`
              }
            >
              <span className="text-base" aria-hidden>
                {item.icon}
              </span>
              {item.label}
            </NavLink>
          ),
        )}
        <NavLink
          to="/profile"
          className={({ isActive }) =>
            `flex flex-col items-center gap-0.5 rounded-lg px-2 py-1.5 text-[11px] font-medium ${
              isActive ? "text-teal-600 dark:text-teal-400" : "text-slate-500 dark:text-slate-400"
            }`
          }
        >
          <span className="text-base" aria-hidden>
            👤
          </span>
          Profile
        </NavLink>
      </nav>
    </div>
  );
}
