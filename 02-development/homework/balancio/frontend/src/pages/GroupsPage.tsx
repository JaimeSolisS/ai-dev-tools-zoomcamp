import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import * as api from "../api/client";
import type { Group } from "../types";
import { useAuth } from "../auth/AuthContext";
import { useUsers } from "../contexts/UsersContext";
import {
  Badge,
  Button,
  EmptyState,
  ErrorText,
  Field,
  Input,
  Label,
  Modal,
  PageHeader,
  Spinner,
  Textarea,
} from "../components/ui";

function CreateGroupModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { users } = useUsers();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [memberIds, setMemberIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function toggle(id: string) {
    setMemberIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.createGroup({ name, description, member_ids: memberIds });
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create group.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Create group" onClose={onClose}>
      <div className="space-y-4">
        <Field>
          <Label>Name</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </Field>
        <Field>
          <Label>Description (optional)</Label>
          <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
        </Field>
        <Field>
          <Label>Members</Label>
          <div className="max-h-48 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-2 dark:border-slate-600">
            {users.map((u) => (
              <label
                key={u.id}
                className="flex items-center gap-2 rounded px-1 py-1 text-sm hover:bg-slate-50 dark:hover:bg-slate-700"
              >
                <input type="checkbox" checked={memberIds.includes(u.id)} onChange={() => toggle(u.id)} />
                {u.display_name}
              </label>
            ))}
          </div>
        </Field>
        <ErrorText message={error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={busy || !name.trim()}>
            {busy ? "Creating…" : "Create group"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export function GroupsPage() {
  const { user } = useAuth();
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  async function load() {
    setGroups(await api.listGroups());
  }

  useEffect(() => {
    load();
  }, []);

  if (!groups) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    );
  }

  const active = groups.filter((g) => g.status === "active");
  const archived = groups.filter((g) => g.status === "archived");

  return (
    <div className="space-y-6">
      <PageHeader
        title="Groups"
        subtitle="Every group you're a member of."
        actions={user?.role === "admin" && <Button onClick={() => setShowCreate(true)}>+ New group</Button>}
      />

      {active.length === 0 ? (
        <EmptyState title="No active groups" hint="Ask your admin to create one." />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {active.map((g) => (
            <Link
              key={g.id}
              to={`/groups/${g.id}`}
              className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-teal-400 dark:border-slate-700 dark:bg-slate-800"
            >
              <h3 className="font-semibold text-slate-800 dark:text-white">{g.name}</h3>
              {g.description && (
                <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{g.description}</p>
              )}
              <p className="mt-2 text-xs text-slate-400">{g.member_ids.length} members</p>
            </Link>
          ))}
        </div>
      )}

      {archived.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-slate-400">Archived groups</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {archived.map((g) => (
              <Link
                key={g.id}
                to={`/groups/${g.id}`}
                className="rounded-xl border border-slate-200 bg-slate-50 p-4 opacity-75 dark:border-slate-700 dark:bg-slate-800/50"
              >
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-slate-700 dark:text-slate-200">{g.name}</h3>
                  <Badge tone="neutral">archived</Badge>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {showCreate && <CreateGroupModal onClose={() => setShowCreate(false)} onCreated={load} />}
    </div>
  );
}
