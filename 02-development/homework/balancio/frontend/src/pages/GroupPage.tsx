import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import * as api from "../api/client";
import type { Category, Expense, Group, GroupBalances, Refund } from "../types";
import { useAuth } from "../auth/AuthContext";
import { useUsers } from "../contexts/UsersContext";
import {
  Badge,
  Button,
  Card,
  EmptyState,
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

function AddMemberModal({
  group,
  onClose,
  onDone,
}: {
  group: Group;
  onClose: () => void;
  onDone: () => void;
}) {
  const { users } = useUsers();
  const [selected, setSelected] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const candidates = users.filter((u) => !group.member_ids.includes(u.id));

  async function submit() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await api.addGroupMember(group.id, selected);
      onDone();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add member.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Add member" onClose={onClose}>
      <div className="space-y-4">
        {candidates.length === 0 ? (
          <p className="text-sm text-slate-500">Everyone is already a member of this group.</p>
        ) : (
          <Field>
            <Label>User</Label>
            <Select value={selected} onChange={(e) => setSelected(e.target.value)}>
              <option value="">Select a user…</option>
              {candidates.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.display_name}
                </option>
              ))}
            </Select>
          </Field>
        )}
        <ErrorText message={error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={busy || !selected}>
            Add
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function EditGroupModal({
  group,
  onClose,
  onDone,
}: {
  group: Group;
  onClose: () => void;
  onDone: () => void;
}) {
  const [name, setName] = useState(group.name);
  const [description, setDescription] = useState(group.description ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.updateGroup(group.id, { name, description });
      onDone();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update group.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Edit group" onClose={onClose}>
      <div className="space-y-4">
        <Field>
          <Label>Name</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field>
          <Label>Description</Label>
          <Input value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <ErrorText message={error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={busy || !name.trim()}>
            Save
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export function GroupPage() {
  const { groupId } = useParams<{ groupId: string }>();
  const { user } = useAuth();
  const { nameOf } = useUsers();
  const navigate = useNavigate();

  const [group, setGroup] = useState<Group | null>(null);
  const [balances, setBalances] = useState<GroupBalances | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [refunds, setRefunds] = useState<Refund[]>([]);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [cursor, setCursor] = useState<number | null>(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [memberFilter, setMemberFilter] = useState("");

  const [showAddMember, setShowAddMember] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<string | null>(null);
  const [showArchive, setShowArchive] = useState(false);
  const [showLeave, setShowLeave] = useState(false);

  const sentinelRef = useRef<HTMLDivElement | null>(null);

  const loadCore = useCallback(async () => {
    if (!groupId) return;
    const [g, b, cats, rfds] = await Promise.all([
      api.getGroup(groupId),
      api.getGroupBalances(groupId),
      api.listCategories(groupId),
      api.listRefunds(),
    ]);
    setGroup(g);
    setBalances(b);
    setCategories(cats);
    setRefunds(rfds.filter((r) => r.group_id === groupId));
  }, [groupId]);

  const loadExpenses = useCallback(
    async (reset: boolean) => {
      if (!groupId) return;
      setLoadingMore(true);
      try {
        const page = await api.listExpenses({
          group_id: groupId,
          search: search || undefined,
          category_id: categoryFilter || undefined,
          member_id: memberFilter || undefined,
          cursor: reset ? 0 : (cursor ?? 0),
          limit: 10,
        });
        setExpenses((prev) => (reset ? page.items : [...prev, ...page.items]));
        setCursor(page.next_cursor);
      } finally {
        setLoadingMore(false);
      }
    },
    [groupId, search, categoryFilter, memberFilter, cursor],
  );

  useEffect(() => {
    loadCore();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupId]);

  useEffect(() => {
    loadExpenses(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupId, search, categoryFilter, memberFilter]);

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && cursor !== null && !loadingMore) {
        loadExpenses(false);
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [cursor, loadingMore, loadExpenses]);

  const members = useMemo(
    () => group?.member_ids.map((id) => ({ id, name: nameOf(id) })) ?? [],
    [group, nameOf],
  );

  if (!group || !balances) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    );
  }

  const isAdmin = user?.role === "admin";
  const myBalance = balances.net[user!.id] ?? "0.00";
  const canLeave = Number(myBalance) === 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title={group.name}
        subtitle={group.description}
        actions={
          <>
            {group.status === "archived" && <Badge tone="neutral">Archived (read-only)</Badge>}
            {isAdmin && group.status === "active" && (
              <>
                <Button variant="secondary" onClick={() => setShowEdit(true)}>
                  Edit
                </Button>
                <Button variant="secondary" onClick={() => setShowAddMember(true)}>
                  + Add member
                </Button>
                <Button variant="danger" onClick={() => setShowArchive(true)}>
                  Archive
                </Button>
              </>
            )}
            {group.status === "active" && (
              <Button onClick={() => navigate(`/groups/${group.id}/expenses/new`)}>+ Add expense</Button>
            )}
          </>
        }
      />

      <ErrorText message={error} />

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <h2 className="mb-2 font-semibold text-slate-800 dark:text-white">Group balance breakdown</h2>
          {balances.pairs.length === 0 ? (
            <p className="text-sm text-slate-400">Everyone in this group is settled up.</p>
          ) : (
            <ul className="space-y-1.5 text-sm">
              {balances.pairs.map((p) => (
                <li key={`${p.from_user_id}-${p.to_user_id}`} className="flex justify-between">
                  <span>
                    {nameOf(p.from_user_id)} owes {nameOf(p.to_user_id)}
                  </span>
                  <Money amount={p.amount} className="font-semibold" />
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold text-slate-800 dark:text-white">Members</h2>
            {!isAdmin && group.status === "active" && (
              <button
                className="text-xs text-teal-600 hover:underline disabled:text-slate-300 dark:text-teal-400"
                disabled={!canLeave}
                onClick={() => setShowLeave(true)}
                title={canLeave ? "" : "You can only leave once your balance is zero"}
              >
                Leave group
              </button>
            )}
          </div>
          <ul className="space-y-1.5 text-sm">
            {members.map((m) => (
              <li key={m.id} className="flex items-center justify-between">
                <span>{m.name}</span>
                <div className="flex items-center gap-2">
                  <Money amount={balances.net[m.id] ?? "0.00"} className="text-xs text-slate-400" />
                  {isAdmin && group.status === "active" && m.id !== user!.id && (
                    <button
                      className="text-xs text-rose-500 hover:underline"
                      onClick={() => setRemoveTarget(m.id)}
                    >
                      Remove
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      {refunds.filter((r) => r.status === "pending").length > 0 && (
        <Card>
          <h2 className="mb-2 font-semibold text-slate-800 dark:text-white">Pending refunds in this group</h2>
          <ul className="space-y-1.5 text-sm">
            {refunds
              .filter((r) => r.status === "pending")
              .map((r) => (
                <li key={r.id} className="flex items-center justify-between">
                  <Link to="/refunds" className="hover:underline">
                    {r.title}
                  </Link>
                  <Badge tone="warning">
                    {r.confirmations.filter((c) => c.confirmed).length}/{r.confirmations.length} confirmed
                  </Badge>
                </li>
              ))}
          </ul>
        </Card>
      )}

      <Card>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold text-slate-800 dark:text-white">Expenses</h2>
          <div className="flex flex-wrap gap-2">
            <Input
              placeholder="Search…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-40"
            />
            <Select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="w-40"
            >
              <option value="">All categories</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
            <Select value={memberFilter} onChange={(e) => setMemberFilter(e.target.value)} className="w-40">
              <option value="">All members</option>
              {members.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </Select>
          </div>
        </div>

        {expenses.length === 0 ? (
          <EmptyState title="No expenses found" hint="Try adjusting your filters or add a new expense." />
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-700">
            {expenses.map((e) => (
              <li key={e.id} className="flex items-center justify-between py-2 text-sm">
                <div>
                  <Link
                    to={`/expenses/${e.id}`}
                    className="font-medium text-slate-700 hover:underline dark:text-slate-200"
                  >
                    {e.title}
                  </Link>
                  <p className="text-xs text-slate-400">
                    {e.expense_date} ·{" "}
                    {categories.find((c) => c.id === e.category_id)?.name ?? "Uncategorized"}
                  </p>
                </div>
                <Money amount={e.amount} className="font-medium" />
              </li>
            ))}
          </ul>
        )}
        <div ref={sentinelRef} className="h-1" />
        {loadingMore && (
          <div className="flex justify-center py-3">
            <Spinner />
          </div>
        )}
      </Card>

      {showAddMember && (
        <AddMemberModal group={group} onClose={() => setShowAddMember(false)} onDone={loadCore} />
      )}
      {showEdit && <EditGroupModal group={group} onClose={() => setShowEdit(false)} onDone={loadCore} />}
      {removeTarget && (
        <ConfirmDialog
          title="Remove member"
          description={`Remove ${nameOf(removeTarget)} from ${group.name}? This is only possible when their balance in this group is zero.`}
          danger
          onConfirm={async () => {
            try {
              await api.removeGroupMember(group.id, removeTarget);
              await loadCore();
            } catch (err) {
              setError(err instanceof Error ? err.message : "Could not remove member.");
              throw err;
            }
          }}
          onClose={() => setRemoveTarget(null)}
        />
      )}
      {showArchive && (
        <ConfirmDialog
          title="Archive group"
          description="Archived groups become read-only. This is only possible when all balances in the group are zero."
          danger
          onConfirm={async () => {
            await api.archiveGroup(group.id);
            await loadCore();
          }}
          onClose={() => setShowArchive(false)}
        />
      )}
      {showLeave && (
        <ConfirmDialog
          title="Leave group"
          description={`Leave ${group.name}? You can rejoin later if the admin adds you back.`}
          danger
          onConfirm={async () => {
            await api.leaveGroup(group.id);
            navigate("/groups");
          }}
          onClose={() => setShowLeave(false)}
        />
      )}
    </div>
  );
}
