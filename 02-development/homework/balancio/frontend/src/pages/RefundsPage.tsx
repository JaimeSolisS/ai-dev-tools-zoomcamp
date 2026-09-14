import { useEffect, useMemo, useState } from "react";
import * as api from "../api/client";
import type { Group, Refund } from "../types";
import { useAuth } from "../auth/AuthContext";
import { useUsers } from "../contexts/UsersContext";
import {
  Badge,
  Button,
  Card,
  ErrorText,
  Field,
  Input,
  Label,
  PageHeader,
  Select,
  Spinner,
} from "../components/ui";
import { Money } from "../components/Money";
import { CommentThread } from "../components/CommentThread";

function NewRefundForm({ groups, onCreated }: { groups: Group[]; onCreated: () => void }) {
  const { users } = useUsers();
  const [groupId, setGroupId] = useState("");
  const [title, setTitle] = useState("");
  const [amount, setAmount] = useState("");
  const [participantIds, setParticipantIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const group = groups.find((g) => g.id === groupId);
  const members = group ? users.filter((u) => group.member_ids.includes(u.id)) : [];

  function toggle(id: string) {
    setParticipantIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.createRefund({ group_id: groupId, title, amount, participant_ids: participantIds });
      setTitle("");
      setAmount("");
      setParticipantIds([]);
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create refund.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="space-y-4">
      <h2 className="font-semibold text-slate-800 dark:text-white">Create a refund</h2>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field>
          <Label>Group</Label>
          <Select
            value={groupId}
            onChange={(e) => {
              setGroupId(e.target.value);
              setParticipantIds([]);
            }}
          >
            <option value="">Select…</option>
            {groups
              .filter((g) => g.status === "active")
              .map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
          </Select>
        </Field>
        <Field>
          <Label>Title</Label>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Returned tickets"
          />
        </Field>
        <Field>
          <Label>Amount</Label>
          <Input
            type="number"
            min="0.01"
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </Field>
      </div>
      {group && (
        <Field>
          <Label>Participants</Label>
          <div className="flex flex-wrap gap-3 rounded-lg border border-slate-200 p-2 dark:border-slate-600">
            {members.map((m) => (
              <label key={m.id} className="flex items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  checked={participantIds.includes(m.id)}
                  onChange={() => toggle(m.id)}
                />
                {m.display_name}
              </label>
            ))}
          </div>
        </Field>
      )}
      <ErrorText message={error} />
      <Button
        onClick={submit}
        disabled={busy || !groupId || !title.trim() || !amount || participantIds.length === 0}
      >
        {busy ? "Creating…" : "Create refund"}
      </Button>
      <p className="text-xs text-slate-400">
        Refunds affect balances only after every selected participant confirms them.
      </p>
    </Card>
  );
}

export function RefundsPage() {
  const { user } = useAuth();
  const { users, nameOf } = useUsers();
  const [refunds, setRefunds] = useState<Refund[] | null>(null);
  const [groups, setGroups] = useState<Group[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  async function load() {
    const [rfds, grps] = await Promise.all([api.listRefunds(), api.listGroups()]);
    setRefunds(rfds);
    setGroups(grps);
  }

  useEffect(() => {
    load();
  }, []);

  const groupName = useMemo(
    () => (id: string) => groups.find((g) => g.id === id)?.name ?? "Unknown group",
    [groups],
  );

  async function confirm(id: string) {
    setError(null);
    try {
      await api.confirmRefund(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not confirm refund.");
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Refunds" subtitle="Standalone refunds that need everyone's confirmation." />
      <NewRefundForm groups={groups} onCreated={load} />
      <ErrorText message={error} />

      <Card>
        <h2 className="mb-2 font-semibold text-slate-800 dark:text-white">All refunds</h2>
        {!refunds ? (
          <Spinner />
        ) : refunds.length === 0 ? (
          <p className="text-sm text-slate-400">No refunds yet.</p>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-700">
            {refunds.map((r) => {
              const myConfirmation = r.confirmations.find((c) => c.user_id === user!.id);
              return (
                <li key={r.id} className="py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
                        {r.title} · <Money amount={r.amount} /> · {groupName(r.group_id)}
                      </p>
                      <p className="text-xs text-slate-400">Created by {nameOf(r.created_by)}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge tone={r.status === "confirmed" ? "success" : "warning"}>{r.status}</Badge>
                      {myConfirmation && !myConfirmation.confirmed && (
                        <Button onClick={() => confirm(r.id)}>Confirm</Button>
                      )}
                      <button
                        className="text-xs text-teal-600 hover:underline dark:text-teal-400"
                        onClick={() => setExpandedId(expandedId === r.id ? null : r.id)}
                      >
                        {expandedId === r.id ? "Hide details" : "Details"}
                      </button>
                    </div>
                  </div>
                  {expandedId === r.id && (
                    <div className="mt-3 space-y-3 rounded-lg bg-slate-50 p-3 dark:bg-slate-700/40">
                      <ul className="space-y-1 text-sm">
                        {r.confirmations.map((c) => (
                          <li key={c.user_id} className="flex justify-between">
                            <span>{nameOf(c.user_id)}</span>
                            <Badge tone={c.confirmed ? "success" : "neutral"}>
                              {c.confirmed ? "Confirmed" : "Pending"}
                            </Badge>
                          </li>
                        ))}
                      </ul>
                      <CommentThread
                        transactionType="refund"
                        transactionId={r.id}
                        users={users}
                        allowed={
                          user?.role === "admin" ||
                          r.created_by === user?.id ||
                          r.participant_ids.includes(user?.id ?? "")
                        }
                      />
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}
