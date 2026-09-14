import type { Expense, Refund, Settlement, PairBalance } from "../types";
import { toCents, fromCents, splitEqually } from "./money";

// The balance engine. Positive net = user is owed money (creditor),
// negative net = user owes money (debtor). All math happens in integer
// cents; net balances always reconcile to zero across all users.

function applyExpense(net: Record<string, number>, expense: Expense) {
  for (const payer of expense.payers) {
    net[payer.user_id] = (net[payer.user_id] ?? 0) + toCents(payer.amount);
  }
  for (const share of expense.shares) {
    net[share.user_id] = (net[share.user_id] ?? 0) - toCents(share.amount);
  }
}

function applyConfirmedRefund(net: Record<string, number>, refund: Refund) {
  net[refund.created_by] = (net[refund.created_by] ?? 0) + toCents(refund.amount);
  const shares = splitEqually(toCents(refund.amount), refund.participant_ids);
  for (const [userId, cents] of shares) {
    net[userId] = (net[userId] ?? 0) - cents;
  }
}

function applySettlement(net: Record<string, number>, settlement: Settlement) {
  const cents = toCents(settlement.amount);
  net[settlement.payer_id] = (net[settlement.payer_id] ?? 0) + cents;
  net[settlement.recipient_id] = (net[settlement.recipient_id] ?? 0) - cents;
}

export function computeGroupNet(
  groupId: string,
  expenses: Expense[],
  refunds: Refund[],
): Record<string, number> {
  const net: Record<string, number> = {};
  for (const e of expenses) {
    if (e.group_id === groupId) applyExpense(net, e);
  }
  for (const r of refunds) {
    if (r.group_id === groupId && r.status === "confirmed") applyConfirmedRefund(net, r);
  }
  return net;
}

export function computeGlobalNet(
  expenses: Expense[],
  refunds: Refund[],
  settlements: Settlement[],
  includePendingSettlements: boolean,
): Record<string, number> {
  const net: Record<string, number> = {};
  for (const e of expenses) applyExpense(net, e);
  for (const r of refunds) {
    if (r.status === "confirmed") applyConfirmedRefund(net, r);
  }
  for (const s of settlements) {
    const effective =
      s.status === "confirmed" ||
      s.status === "reversal_pending" ||
      (includePendingSettlements && s.status === "pending");
    if (effective) applySettlement(net, s);
  }
  return net;
}

/** Greedy debt simplification: matches the largest creditor against the
 * largest debtor repeatedly. Ties are broken by user id for determinism. */
export function simplify(net: Record<string, number>): PairBalance[] {
  const creditors = Object.entries(net)
    .filter(([, v]) => v > 0)
    .map(([id, v]) => ({ id, amt: v }))
    .sort((a, b) => b.amt - a.amt || a.id.localeCompare(b.id));
  const debtors = Object.entries(net)
    .filter(([, v]) => v < 0)
    .map(([id, v]) => ({ id, amt: -v }))
    .sort((a, b) => b.amt - a.amt || a.id.localeCompare(b.id));

  const results: PairBalance[] = [];
  let i = 0;
  let j = 0;
  while (i < creditors.length && j < debtors.length) {
    const c = creditors[i];
    const d = debtors[j];
    const amt = Math.min(c.amt, d.amt);
    if (amt > 0) {
      results.push({ from_user_id: d.id, to_user_id: c.id, amount: fromCents(amt) });
    }
    c.amt -= amt;
    d.amt -= amt;
    if (c.amt === 0) i++;
    if (d.amt === 0) j++;
  }
  return results;
}

export function netToStrings(net: Record<string, number>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [id, cents] of Object.entries(net)) out[id] = fromCents(cents);
  return out;
}
