import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { AuthProvider } from "./auth/AuthContext";
import { ThemeProvider } from "./contexts/ThemeContext";
import { UsersProvider } from "./contexts/UsersContext";
import { RequireAdmin, RequireAuth, RedirectIfAuthed } from "./components/RouteGuards";
import { Layout } from "./components/Layout";

import { LoginPage } from "./pages/LoginPage";
import { SetupPage } from "./pages/SetupPage";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { DashboardPage } from "./pages/DashboardPage";
import { GroupsPage } from "./pages/GroupsPage";
import { GroupPage } from "./pages/GroupPage";
import { ExpenseFormPage } from "./pages/ExpenseFormPage";
import { ExpensePage } from "./pages/ExpensePage";
import { SettlementsPage } from "./pages/SettlementsPage";
import { RefundsPage } from "./pages/RefundsPage";
import { HistoryPage } from "./pages/HistoryPage";
import { ProfilePage } from "./pages/ProfilePage";
import { AdminPage } from "./pages/AdminPage";

function AppProviders({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <UsersProvider>
        <ThemeProvider>{children}</ThemeProvider>
      </UsersProvider>
    </AuthProvider>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppProviders>
        <Routes>
          <Route
            path="/login"
            element={
              <RedirectIfAuthed>
                <LoginPage />
              </RedirectIfAuthed>
            }
          />
          <Route
            path="/setup"
            element={
              <RedirectIfAuthed>
                <SetupPage />
              </RedirectIfAuthed>
            }
          />

          <Route element={<RequireAuth />}>
            <Route path="/change-password" element={<ChangePasswordPage />} />

            <Route element={<Layout />}>
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/groups" element={<GroupsPage />} />
              <Route path="/groups/:groupId" element={<GroupPage />} />
              <Route path="/groups/:groupId/expenses/new" element={<ExpenseFormPage mode="create" />} />
              <Route path="/expenses/:expenseId" element={<ExpensePage />} />
              <Route path="/expenses/:expenseId/edit" element={<ExpenseFormPage mode="edit" />} />
              <Route path="/settlements" element={<SettlementsPage />} />
              <Route path="/refunds" element={<RefundsPage />} />
              <Route path="/history" element={<HistoryPage />} />
              <Route path="/profile" element={<ProfilePage />} />
              <Route element={<RequireAdmin />}>
                <Route path="/admin" element={<AdminPage />} />
              </Route>
            </Route>
          </Route>

          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AppProviders>
    </BrowserRouter>
  );
}
