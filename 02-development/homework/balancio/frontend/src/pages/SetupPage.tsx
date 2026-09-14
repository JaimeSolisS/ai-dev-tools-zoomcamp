import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import * as api from "../api/client";
import { Button, Card, ErrorText, Field, Input, Label } from "../components/ui";
import { APP_NAME } from "../config";

export function SetupPage() {
  const { setup } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.getSetupStatus().then(({ admin_exists }) => {
      if (admin_exists) navigate("/login", { replace: true });
    });
  }, [navigate]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await setup({ username, display_name: displayName, password });
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not complete setup.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 dark:bg-slate-900">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-teal-700 dark:text-teal-400">{APP_NAME}</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Welcome! Create the first admin account to get started.
          </p>
        </div>
        <Card>
          <form className="space-y-4" onSubmit={handleSubmit}>
            <Field>
              <Label>Username</Label>
              <Input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required />
            </Field>
            <Field>
              <Label>Display name</Label>
              <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
            </Field>
            <Field>
              <Label>Password (min. 8 characters)</Label>
              <Input
                type="password"
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </Field>
            <Field>
              <Label>Confirm password</Label>
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
              {busy ? "Creating…" : "Create admin account"}
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
