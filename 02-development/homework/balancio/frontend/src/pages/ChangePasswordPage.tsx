import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import * as api from "../api/client";
import { Button, Card, ErrorText, Field, Input, Label } from "../components/ui";

export function ChangePasswordPage() {
  const { user, setUser, logout } = useAuth();
  const navigate = useNavigate();
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (newPassword !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await api.changePassword(oldPassword, newPassword);
      setUser(updated);
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 dark:bg-slate-900">
      <div className="w-full max-w-sm space-y-4">
        <Card>
          <h1 className="mb-1 text-lg font-semibold text-slate-900 dark:text-white">
            {user?.must_change_password ? "Choose a new password" : "Change your password"}
          </h1>
          <p className="mb-4 text-sm text-slate-500 dark:text-slate-400">
            {user?.must_change_password
              ? "You're using a temporary password. Set a new one to continue."
              : "Update your account password."}
          </p>
          <form className="space-y-4" onSubmit={handleSubmit}>
            <Field>
              <Label>Current password</Label>
              <Input
                type="password"
                value={oldPassword}
                onChange={(e) => setOldPassword(e.target.value)}
                required
                autoFocus
              />
            </Field>
            <Field>
              <Label>New password (min. 8 characters)</Label>
              <Input
                type="password"
                minLength={8}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
              />
            </Field>
            <Field>
              <Label>Confirm new password</Label>
              <Input
                type="password"
                minLength={8}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
              />
            </Field>
            <ErrorText message={error} />
            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? "Saving…" : "Save new password"}
            </Button>
          </form>
        </Card>
        <button
          className="w-full text-center text-sm text-slate-500 hover:underline dark:text-slate-400"
          onClick={async () => {
            await logout();
            navigate("/login");
          }}
        >
          Log out instead
        </button>
      </div>
    </div>
  );
}
