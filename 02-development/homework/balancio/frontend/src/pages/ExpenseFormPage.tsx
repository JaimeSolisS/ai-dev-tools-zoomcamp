import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import * as api from "../api/client";
import type { Category, Expense, Group, Payer } from "../types";
import type { ExpenseInput } from "../api/client";
import { useUsers } from "../contexts/UsersContext";
import { toCents, fromCents, splitEqually } from "../utils/money";
import {
  Button,
  Card,
  ErrorText,
  Field,
  Input,
  Label,
  PageHeader,
  Select,
  Spinner,
  Textarea,
} from "../components/ui";
import { Money } from "../components/Money";

interface LocationState {
  draft?: ExpenseInput;
}

export function ExpenseFormPage({ mode }: { mode: "create" | "edit" }) {
  const { groupId, expenseId } = useParams<{ groupId: string; expenseId: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const { users, nameOf } = useUsers();

  const draft = (location.state as LocationState | null)?.draft;

  const [group, setGroup] = useState<Group | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [blockedError, setBlockedError] = useState<string | null>(null);

  const [title, setTitle] = useState(draft?.title ?? "");
  const [amount, setAmount] = useState(draft?.amount ?? "");
  const [date, setDate] = useState(draft?.expense_date ?? new Date().toISOString().slice(0, 10));
  const [categoryId, setCategoryId] = useState<string>(draft?.category_id ?? "");
  const [note, setNote] = useState(draft?.note ?? "");
  const [tagsText, setTagsText] = useState((draft?.tags ?? []).join(", "));
  const [payerIds, setPayerIds] = useState<string[]>(draft?.payers.map((p) => p.user_id) ?? []);
  const [payerAmounts, setPayerAmounts] = useState<Record<string, string>>(
    Object.fromEntries((draft?.payers ?? []).map((p) => [p.user_id, p.amount])),
  );
  const [participantIds, setParticipantIds] = useState<string[]>(draft?.participant_ids ?? []);
  const [memberSearch, setMemberSearch] = useState("");

  useEffect(() => {
    async function load() {
      setLoading(true);
      const gid = groupId ?? draft?.group_id;
      let g: Group | null = null;
      if (expenseId) {
        const currentExpense: Expense = await api.getExpense(expenseId);
        g = await api.getGroup(currentExpense.group_id);
        setTitle(currentExpense.title);
        setAmount(currentExpense.amount);
        setDate(currentExpense.expense_date);
        setCategoryId(currentExpense.category_id ?? "");
        setNote(currentExpense.note ?? "");
        setTagsText(currentExpense.tags.join(", "));
        setPayerIds(currentExpense.payers.map((p) => p.user_id));
        setPayerAmounts(Object.fromEntries(currentExpense.payers.map((p) => [p.user_id, p.amount])));
        setParticipantIds(currentExpense.participant_ids);
      } else if (gid) {
        g = await api.getGroup(gid);
      }
      setGroup(g);
      if (g) setCategories(await api.listCategories(g.id));
      setLoading(false);
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupId, expenseId]);

  const members = useMemo(
    () => (group ? users.filter((u) => group.member_ids.includes(u.id)) : []),
    [group, users],
  );

  const filteredMembers = useMemo(
    () => members.filter((m) => m.display_name.toLowerCase().includes(memberSearch.toLowerCase())),
    [members, memberSearch],
  );

  const payerTotalCents = payerIds.reduce((sum, id) => sum + toCents(payerAmounts[id] || "0"), 0);
  const amountCents = toCents(amount || "0");
  const payerMismatch = payerIds.length > 0 && payerTotalCents !== amountCents;

  const shares = useMemo(() => {
    if (participantIds.length === 0 || !amount) return [];
    const cents = splitEqually(amountCents, participantIds);
    return participantIds.map((id) => ({ id, amount: fromCents(cents.get(id) ?? 0) }));
  }, [participantIds, amountCents, amount]);

  function togglePayer(id: string) {
    setPayerIds((ids) => {
      if (ids.includes(id)) {
        const next = ids.filter((x) => x !== id);
        setPayerAmounts((a) => {
          const next = { ...a };
          delete next[id];
          return next;
        });
        return next;
      }
      return [...ids, id];
    });
  }

  function toggleParticipant(id: string) {
    setParticipantIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  }

  function fillRemainingToOnePayer(id: string) {
    setPayerAmounts((a) => ({ ...a, [id]: amount || "0.00" }));
  }

  async function handleSubmit() {
    if (!group) return;
    setBusy(true);
    setError(null);
    setBlockedError(null);
    const payers: Payer[] = payerIds.map((id) => ({ user_id: id, amount: payerAmounts[id] || "0.00" }));
    const tags = tagsText
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    const input: ExpenseInput = {
      group_id: group.id,
      title,
      amount,
      expense_date: date,
      category_id: categoryId || null,
      note,
      tags,
      payers,
      participant_ids: participantIds,
    };
    try {
      if (mode === "edit" && expenseId) {
        await api.updateExpense(expenseId, input);
        navigate(`/expenses/${expenseId}`);
      } else {
        const created = await api.createExpense(input);
        navigate(`/expenses/${created.id}`);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not save expense.";
      if (message.includes("confirmed settlement activity")) setBlockedError(message);
      else setError(message);
    } finally {
      setBusy(false);
    }
  }

  if (loading || !group) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    );
  }

  const isValid =
    title.trim() &&
    amount &&
    amountCents > 0 &&
    payerIds.length > 0 &&
    !payerMismatch &&
    participantIds.length > 0;

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <PageHeader title={mode === "edit" ? "Edit expense" : "Add expense"} subtitle={`In ${group.name}`} />

      <Card className="space-y-5">
        <Field>
          <Label>Title</Label>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Groceries"
            autoFocus
          />
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field>
            <Label>Amount</Label>
            <Input
              type="number"
              min="0.01"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00"
            />
          </Field>
          <Field>
            <Label>Date</Label>
            <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </Field>
        </div>

        <Field>
          <Label>Category</Label>
          <Select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">Uncategorized</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>

        <Field>
          <Label>Note (optional)</Label>
          <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
        </Field>

        <Field>
          <Label>Tags (comma separated)</Label>
          <Input
            value={tagsText}
            onChange={(e) => setTagsText(e.target.value)}
            placeholder="vacation, birthday"
          />
        </Field>

        <Field>
          <Label>Payers</Label>
          <div className="space-y-1 rounded-lg border border-slate-200 p-2 dark:border-slate-600">
            {members.map((m) => (
              <div key={m.id} className="flex items-center gap-2">
                <label className="flex flex-1 items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={payerIds.includes(m.id)}
                    onChange={() => togglePayer(m.id)}
                  />
                  {m.display_name}
                </label>
                {payerIds.includes(m.id) && (
                  <div className="flex items-center gap-1">
                    <Input
                      type="number"
                      step="0.01"
                      className="w-24"
                      value={payerAmounts[m.id] ?? ""}
                      onChange={(e) => setPayerAmounts((a) => ({ ...a, [m.id]: e.target.value }))}
                    />
                    {payerIds.length === 1 && (
                      <button
                        type="button"
                        className="text-xs text-teal-600 hover:underline dark:text-teal-400"
                        onClick={() => fillRemainingToOnePayer(m.id)}
                      >
                        full amount
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
          <p className={`mt-1 text-xs ${payerMismatch ? "text-rose-500" : "text-slate-400"}`}>
            Paid so far: <Money amount={fromCents(payerTotalCents)} /> of <Money amount={amount || "0"} />
            {payerMismatch && " — payer amounts must equal the total."}
          </p>
        </Field>

        <Field>
          <Label>Participants</Label>
          {members.length > 8 && (
            <Input
              className="mb-2"
              placeholder="Search members…"
              value={memberSearch}
              onChange={(e) => setMemberSearch(e.target.value)}
            />
          )}
          <div className="space-y-1 rounded-lg border border-slate-200 p-2 dark:border-slate-600">
            <label className="flex items-center gap-2 border-b border-slate-100 pb-1 text-sm font-medium dark:border-slate-700">
              <input
                type="checkbox"
                checked={participantIds.length === members.length}
                onChange={() =>
                  setParticipantIds(participantIds.length === members.length ? [] : members.map((m) => m.id))
                }
              />
              Select all
            </label>
            {filteredMembers.map((m) => (
              <label key={m.id} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={participantIds.includes(m.id)}
                  onChange={() => toggleParticipant(m.id)}
                />
                {m.display_name}
              </label>
            ))}
          </div>
        </Field>

        {shares.length > 0 && (
          <Field>
            <Label>Calculated equal shares</Label>
            <ul className="rounded-lg bg-slate-50 p-2 text-sm dark:bg-slate-700/50">
              {shares.map((s) => (
                <li key={s.id} className="flex justify-between py-0.5">
                  <span>{nameOf(s.id)}</span>
                  <Money amount={s.amount} />
                </li>
              ))}
            </ul>
          </Field>
        )}

        <ErrorText message={error} />
        {blockedError && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
            {blockedError}
          </p>
        )}

        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => navigate(-1)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={busy || !isValid}>
            {busy ? "Saving…" : mode === "edit" ? "Save changes" : "Add expense"}
          </Button>
        </div>
      </Card>
    </div>
  );
}
