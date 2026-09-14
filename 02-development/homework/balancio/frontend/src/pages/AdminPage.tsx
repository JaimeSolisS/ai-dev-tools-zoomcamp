import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import * as api from "../api/client";
import type { AdminOverview } from "../api/client";
import type { Category, Group, Refund, Settlement, User } from "../types";
import { useUsers } from "../contexts/UsersContext";
import {
  Badge,
  Button,
  Card,
  ErrorText,
  Field,
  Input,
  Label,
  Modal,
  PageHeader,
  Select,
  Spinner,
} from "../components/ui";
import { Money } from "../components/Money";
import { ConfirmDialog } from "../components/ConfirmDialog";

const TABS = ["Overview", "Users", "Groups", "Categories"] as const;
type Tab = (typeof TABS)[number];

function CreateUserModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.createUser({ username, display_name: displayName, temporary_password: password });
      onDone();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create user.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Create user" onClose={onClose}>
      <div className="space-y-4">
        <Field>
          <Label>Username</Label>
          <Input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
        </Field>
        <Field>
          <Label>Display name</Label>
          <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        </Field>
        <Field>
          <Label>Temporary password (min. 8 characters)</Label>
          <Input type="text" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <ErrorText message={error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={busy || !username.trim() || password.length < 8}>
            Create
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function ResetPasswordModal({
  user,
  onClose,
  onDone,
}: {
  user: User;
  onClose: () => void;
  onDone: () => void;
}) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.resetPassword(user.id, password);
      onDone();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reset password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={`Reset password for ${user.display_name}`} onClose={onClose}>
      <div className="space-y-4">
        <Field>
          <Label>New temporary password (min. 8 characters)</Label>
          <Input value={password} onChange={(e) => setPassword(e.target.value)} autoFocus />
        </Field>
        <ErrorText message={error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={busy || password.length < 8}>
            Reset password
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function UsersTab() {
  const { users, refresh } = useUsers();
  const [showCreate, setShowCreate] = useState(false);
  const [resetTarget, setResetTarget] = useState<User | null>(null);
  const [deactivateTarget, setDeactivateTarget] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggleActive(u: User) {
    setError(null);
    try {
      if (u.is_active) setDeactivateTarget(u);
      else {
        await api.activateUser(u.id);
        await refresh();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update user.");
    }
  }

  async function forceChange(u: User) {
    setError(null);
    try {
      await api.forcePasswordChange(u.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not force password change.");
    }
  }

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-semibold text-slate-800 dark:text-white">Users</h2>
        <Button onClick={() => setShowCreate(true)}>+ New user</Button>
      </div>
      <ErrorText message={error} />
      <ul className="divide-y divide-slate-100 dark:divide-slate-700">
        {users.map((u) => (
          <li key={u.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
            <div>
              <p className="font-medium text-slate-700 dark:text-slate-200">
                {u.display_name} <span className="text-xs text-slate-400">@{u.username}</span>
              </p>
              <div className="mt-0.5 flex gap-1.5">
                {u.role === "admin" && <Badge tone="info">admin</Badge>}
                {!u.is_active && <Badge tone="danger">deactivated</Badge>}
                {u.must_change_password && <Badge tone="warning">must change password</Badge>}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => setResetTarget(u)}>
                Reset password
              </Button>
              {u.role !== "admin" && (
                <>
                  {!u.must_change_password && (
                    <Button variant="secondary" onClick={() => forceChange(u)}>
                      Force change
                    </Button>
                  )}
                  <Button variant={u.is_active ? "danger" : "primary"} onClick={() => toggleActive(u)}>
                    {u.is_active ? "Deactivate" : "Activate"}
                  </Button>
                </>
              )}
            </div>
          </li>
        ))}
      </ul>

      {showCreate && <CreateUserModal onClose={() => setShowCreate(false)} onDone={refresh} />}
      {resetTarget && (
        <ResetPasswordModal user={resetTarget} onClose={() => setResetTarget(null)} onDone={refresh} />
      )}
      {deactivateTarget && (
        <ConfirmDialog
          title="Deactivate user"
          description={`Deactivate ${deactivateTarget.display_name}? This is only possible when their global balance is zero.`}
          danger
          onConfirm={async () => {
            try {
              await api.deactivateUser(deactivateTarget.id);
              await refresh();
            } catch (err) {
              setError(err instanceof Error ? err.message : "Could not deactivate user.");
              throw err;
            }
          }}
          onClose={() => setDeactivateTarget(null)}
        />
      )}
    </Card>
  );
}

function GroupsTab({ groups }: { groups: Group[] }) {
  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-semibold text-slate-800 dark:text-white">Groups</h2>
        <Link to="/groups" className="text-sm text-teal-600 hover:underline dark:text-teal-400">
          Manage on Groups page →
        </Link>
      </div>
      <ul className="divide-y divide-slate-100 dark:divide-slate-700">
        {groups.map((g) => (
          <li key={g.id} className="flex items-center justify-between py-2 text-sm">
            <Link to={`/groups/${g.id}`} className="hover:underline">
              {g.name}
            </Link>
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400">{g.member_ids.length} members</span>
              <Badge tone={g.status === "active" ? "success" : "neutral"}>{g.status}</Badge>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function CategoriesTab({ groups }: { groups: Group[] }) {
  const [categories, setCategories] = useState<Category[]>([]);
  const [name, setName] = useState("");
  const [scope, setScope] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const global = await api.listCategories();
    setCategories(global);
  }

  useEffect(() => {
    load();
  }, []);

  async function create() {
    setError(null);
    try {
      await api.createCategory({ name, group_id: scope || null });
      setName("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create category.");
    }
  }

  async function remove(id: string) {
    setError(null);
    try {
      await api.deleteCategory(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete category.");
    }
  }

  const globalCategories = categories.filter((c) => c.group_id === null);

  return (
    <Card className="space-y-4">
      <h2 className="font-semibold text-slate-800 dark:text-white">Categories</h2>
      <div className="flex flex-wrap gap-2">
        <Input
          placeholder="New category name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-48"
        />
        <Select value={scope} onChange={(e) => setScope(e.target.value)} className="w-48">
          <option value="">Global</option>
          {groups.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name} only
            </option>
          ))}
        </Select>
        <Button onClick={create} disabled={!name.trim()}>
          Add
        </Button>
      </div>
      <ErrorText message={error} />
      <div>
        <h3 className="mb-1 text-xs font-semibold uppercase text-slate-400">Global categories</h3>
        <ul className="flex flex-wrap gap-2">
          {globalCategories.map((c) => (
            <li
              key={c.id}
              className="flex items-center gap-1 rounded-full bg-slate-100 px-2 py-1 text-xs dark:bg-slate-700"
            >
              {c.name}
              <button className="text-rose-500" onClick={() => remove(c.id)}>
                ✕
              </button>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  );
}

export function AdminPage() {
  const { nameOf } = useUsers();
  const [tab, setTab] = useState<Tab>("Overview");
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [groups, setGroups] = useState<Group[]>([]);
  const [settlements, setSettlements] = useState<Settlement[]>([]);
  const [refunds, setRefunds] = useState<Refund[]>([]);

  useEffect(() => {
    async function load() {
      const [ov, grps, stls, rfds] = await Promise.all([
        api.getAdminOverview(),
        api.listGroups(),
        api.listSettlements(),
        api.listRefunds(),
      ]);
      setOverview(ov);
      setGroups(grps);
      setSettlements(stls);
      setRefunds(rfds);
    }
    load();
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader title="Admin" subtitle="Manage users, groups, categories, and keep an eye on the system." />

      <div className="flex gap-1 border-b border-slate-200 dark:border-slate-700">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm font-medium ${
              tab === t
                ? "border-b-2 border-teal-600 text-teal-600 dark:text-teal-400"
                : "text-slate-500 hover:text-slate-700 dark:text-slate-400"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Overview" &&
        (overview ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                ["Users", overview.users_count],
                ["Active users", overview.active_users_count],
                ["Groups", overview.groups_count],
                ["Active groups", overview.active_groups_count],
                ["Expenses", overview.expenses_count],
                ["Pending settlements", overview.pending_settlements_count],
                ["Pending refunds", overview.pending_refunds_count],
              ].map(([label, value]) => (
                <Card key={label as string} className="text-center">
                  <p className="text-2xl font-bold text-slate-900 dark:text-white">{value}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
                </Card>
              ))}
            </div>
            <Card>
              <h2 className="mb-2 font-semibold text-slate-800 dark:text-white">Pending settlements</h2>
              {settlements.filter((s) => s.status === "pending" || s.status === "reversal_pending").length ===
              0 ? (
                <p className="text-sm text-slate-400">None right now.</p>
              ) : (
                <ul className="space-y-1 text-sm">
                  {settlements
                    .filter((s) => s.status === "pending" || s.status === "reversal_pending")
                    .map((s) => (
                      <li key={s.id} className="flex justify-between">
                        <span>
                          {nameOf(s.payer_id)} → {nameOf(s.recipient_id)}
                        </span>
                        <Money amount={s.amount} />
                      </li>
                    ))}
                </ul>
              )}
              <Link
                to="/settlements"
                className="mt-2 inline-block text-sm text-teal-600 hover:underline dark:text-teal-400"
              >
                Go to Settlements →
              </Link>
            </Card>
            <Card>
              <h2 className="mb-2 font-semibold text-slate-800 dark:text-white">Pending refunds</h2>
              {refunds.filter((r) => r.status === "pending").length === 0 ? (
                <p className="text-sm text-slate-400">None right now.</p>
              ) : (
                <ul className="space-y-1 text-sm">
                  {refunds
                    .filter((r) => r.status === "pending")
                    .map((r) => (
                      <li key={r.id} className="flex justify-between">
                        <span>{r.title}</span>
                        <Money amount={r.amount} />
                      </li>
                    ))}
                </ul>
              )}
              <Link
                to="/refunds"
                className="mt-2 inline-block text-sm text-teal-600 hover:underline dark:text-teal-400"
              >
                Go to Refunds →
              </Link>
            </Card>
          </div>
        ) : (
          <Spinner />
        ))}

      {tab === "Users" && <UsersTab />}
      {tab === "Groups" && <GroupsTab groups={groups} />}
      {tab === "Categories" && <CategoriesTab groups={groups} />}
    </div>
  );
}
