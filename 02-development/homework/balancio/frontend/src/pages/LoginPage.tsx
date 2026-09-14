import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import * as api from "../api/client";
import { DEMO_CREDENTIALS } from "../api/mockData";
import { Button, Card, ErrorText, Field, Input, Label } from "../components/ui";
import { APP_NAME } from "../config";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [checkingSetup, setCheckingSetup] = useState(true);

  useEffect(() => {
    api.hasAdmin().then((exists) => {
      if (!exists) navigate("/setup", { replace: true });
      else setCheckingSetup(false);
    });
  }, [navigate]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await login(username, password);
      navigate(user.must_change_password ? "/change-password" : "/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not log in.");
    } finally {
      setBusy(false);
    }
  }

  if (checkingSetup) return null;

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 dark:bg-slate-900">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-teal-700 dark:text-teal-400">{APP_NAME}</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Split expenses. Settle balances.</p>
        </div>
        <Card>
          <form className="space-y-4" onSubmit={handleSubmit}>
            <Field>
              <Label>Username</Label>
              <Input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required />
            </Field>
            <Field>
              <Label>Password</Label>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </Field>
            <ErrorText message={error} />
            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? "Logging in…" : "Log in"}
            </Button>
          </form>
        </Card>
        <Card className="text-left text-xs text-slate-500 dark:text-slate-400">
          <p className="mb-2 font-semibold text-slate-600 dark:text-slate-300">Demo accounts</p>
          <ul className="space-y-1">
            {DEMO_CREDENTIALS.map((c) => (
              <li key={c.username} className="flex justify-between gap-2">
                <span>
                  <code className="rounded bg-slate-100 px-1 dark:bg-slate-700">{c.username}</code> /{" "}
                  <code className="rounded bg-slate-100 px-1 dark:bg-slate-700">{c.password}</code>
                </span>
                <span className="text-slate-400">{c.note}</span>
              </li>
            ))}
          </ul>
          <button
            className="mt-3 text-teal-600 hover:underline dark:text-teal-400"
            onClick={async () => {
              await api.resetDemoData();
              window.location.reload();
            }}
          >
            Reset demo data
          </button>
        </Card>
      </div>
    </div>
  );
}
