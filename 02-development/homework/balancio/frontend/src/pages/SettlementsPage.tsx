import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import * as api from "../api/client";
import type { Settlement } from "../types";
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
import { ConfirmDialog } from "../components/ConfirmDialog";

const statusTone: Record<Settlement["status"], "neutral" | "success" | "warning" | "danger" | "info"> = {
  pending: "info",
  confirmed: "success",
  rejected: "danger",
  cancelled: "neutral",
  reversal_pending: "warning",
  reversed: "neutral",
};

function NewSettlementForm({ onCreated }: { onCreated: () => void }) {
  const { user } = useAuth();
  const { users } = useUsers();
  const [params] = useSearchParams();
  const [recipientId, setRecipientId] = useState(params.get("recipient") ?? "");
  const [amount, setAmount] = useState(params.get("amount") ?? "");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const candidates = users.filter((u) => u.id !== user!.id);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.createSettlement({ payer_id: user!.id, recipient_id: recipientId, amount, note });
      setAmount("");
      setNote("");
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create settlement.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="space-y-4">
      <h2 className="font-semibold text-slate-800 dark:text-white">Record a payment</h2>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field>
          <Label>Pay to</Label>
          <Select value={recipientId} onChange={(e) => setRecipientId(e.target.value)}>
            <option value="">Select…</option>
            {candidates.map((u) => (
              <option key={u.id} value={u.id}>
                {u.display_name}
              </option>
            ))}
          </Select>
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
        <Field>
          <Label>Note (optional)</Label>
          <Input value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
      </div>
      <ErrorText message={error} />
      <Button onClick={submit} disabled={busy || !recipientId || !amount}>
        {busy ? "Recording…" : "Record payment"}
      </Button>
      <p className="text-xs text-slate-400">
        Partial payments and overpayments are both fine — the recipient will confirm before it's final.
      </p>
    </Card>
  );
}

export function SettlementsPage() {
  const { user } = useAuth();
  const { nameOf } = useUsers();
  const [settlements, setSettlements] = useState<Settlement[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editTarget, setEditTarget] = useState<Settlement | null>(null);
  const [editAmount, setEditAmount] = useState("");

  async function load() {
    setSettlements(await api.listSettlements());
  }

  useEffect(() => {
    load();
  }, []);

  const meId = user!.id;

  const mine = useMemo(
    () => (settlements ?? []).filter((s) => s.payer_id === meId || s.recipient_id === meId),
    [settlements, meId],
  );
  const others = useMemo(
    () => (settlements ?? []).filter((s) => s.payer_id !== meId && s.recipient_id !== meId),
    [settlements, meId],
  );

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  function Row({ s }: { s: Settlement }) {
    const iAmPayer = s.payer_id === meId;
    const iAmRecipient = s.recipient_id === meId;
    return (
      <li className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
        <div>
          <p>
            {nameOf(s.payer_id)} → {nameOf(s.recipient_id)}{" "}
            <Money amount={s.amount} className="font-semibold" />
          </p>
          {s.note && <p className="text-xs text-slate-400">{s.note}</p>}
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={statusTone[s.status]}>{s.status.replace("_", " ")}</Badge>
          {s.status === "pending" && iAmRecipient && (
            <>
              <Button onClick={() => run(() => api.confirmSettlement(s.id))}>Confirm</Button>
              <Button variant="danger" onClick={() => run(() => api.rejectSettlement(s.id))}>
                Reject
              </Button>
            </>
          )}
          {s.status === "pending" && iAmPayer && (
            <>
              <Button
                variant="secondary"
                onClick={() => {
                  setEditTarget(s);
                  setEditAmount(s.amount);
                }}
              >
                Edit
              </Button>
              <Button variant="danger" onClick={() => run(() => api.cancelSettlement(s.id))}>
                Cancel
              </Button>
            </>
          )}
          {s.status === "confirmed" && (iAmPayer || iAmRecipient) && (
            <Button variant="secondary" onClick={() => run(() => api.requestReversal(s.id))}>
              Request reversal
            </Button>
          )}
          {s.status === "reversal_pending" &&
            (iAmPayer || iAmRecipient) &&
            s.reversal_requested_by !== meId && (
              <>
                <Button onClick={() => run(() => api.confirmReversal(s.id))}>Confirm reversal</Button>
                <Button variant="danger" onClick={() => run(() => api.rejectReversal(s.id))}>
                  Reject reversal
                </Button>
              </>
            )}
          {s.status === "reversal_pending" && s.reversal_requested_by === meId && (
            <span className="text-xs text-slate-400">
              Waiting for {nameOf(iAmPayer ? s.recipient_id : s.payer_id)}
            </span>
          )}
        </div>
      </li>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Settlements" subtitle="Record payments and confirm what you've received." />
      <NewSettlementForm onCreated={load} />
      <ErrorText message={error} />

      <Card>
        <h2 className="mb-2 font-semibold text-slate-800 dark:text-white">Your settlements</h2>
        {!settlements ? (
          <Spinner />
        ) : mine.length === 0 ? (
          <p className="text-sm text-slate-400">No settlements yet.</p>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-700">
            {mine.map((s) => (
              <Row key={s.id} s={s} />
            ))}
          </ul>
        )}
      </Card>

      {user?.role === "admin" && others.length > 0 && (
        <Card>
          <h2 className="mb-2 font-semibold text-slate-800 dark:text-white">All other settlements</h2>
          <ul className="divide-y divide-slate-100 dark:divide-slate-700">
            {others.map((s) => (
              <Row key={s.id} s={s} />
            ))}
          </ul>
        </Card>
      )}

      {editTarget && (
        <ConfirmDialog
          title="Edit settlement"
          confirmLabel="Save"
          description={
            <div className="space-y-2">
              <Label>Amount</Label>
              <Input
                type="number"
                min="0.01"
                step="0.01"
                value={editAmount}
                onChange={(e) => setEditAmount(e.target.value)}
              />
            </div>
          }
          onConfirm={async () => {
            await api.updateSettlement(editTarget.id, { amount: editAmount });
            await load();
          }}
          onClose={() => setEditTarget(null)}
        />
      )}
    </div>
  );
}
