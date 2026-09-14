import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../contexts/ThemeContext";
import * as api from "../api/client";
import { Button, Card, ErrorText, Field, Input, Label, PageHeader } from "../components/ui";

export function ProfilePage() {
  const { user, setUser, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const navigate = useNavigate();
  const [displayName, setDisplayName] = useState(user!.display_name);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  async function saveDisplayName() {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await api.updateUser(user!.id, { display_name: displayName });
      setUser(updated);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <PageHeader title="Profile" subtitle="Manage your account." />

      <Card className="space-y-4">
        <Field>
          <Label>Username</Label>
          <Input value={user!.username} disabled />
        </Field>
        <Field>
          <Label>Display name</Label>
          <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        </Field>
        <ErrorText message={error} />
        {saved && <p className="text-sm text-emerald-600">Saved.</p>}
        <Button onClick={saveDisplayName} disabled={busy || !displayName.trim()}>
          Save
        </Button>
      </Card>

      <Card className="space-y-3">
        <h2 className="font-semibold text-slate-800 dark:text-white">Appearance</h2>
        <div className="flex gap-2">
          <Button variant={theme === "light" ? "primary" : "secondary"} onClick={() => setTheme("light")}>
            ☀️ Light
          </Button>
          <Button variant={theme === "dark" ? "primary" : "secondary"} onClick={() => setTheme("dark")}>
            🌙 Dark
          </Button>
        </div>
      </Card>

      <Card className="space-y-3">
        <h2 className="font-semibold text-slate-800 dark:text-white">Security</h2>
        <Button variant="secondary" onClick={() => navigate("/change-password")}>
          Change password
        </Button>
      </Card>

      <Button
        variant="ghost"
        onClick={async () => {
          await logout();
          navigate("/login");
        }}
      >
        Log out
      </Button>
    </div>
  );
}
