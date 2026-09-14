import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import * as api from "../api/client";
import type { GlobalBalances, Settlement, Refund, Expense, Group, PairBalance } from "../types";
import { useAuth } from "../auth/AuthContext";
import { useUsers } from "../contexts/UsersContext";
import { Badge, Button, Card, EmptyState, PageHeader, Spinner } from "../components/ui";
import { Money } from "../components/Money";

function pairsInvolving(pairs: PairBalance[], userId: string) {
  return pairs.filter((p) => p.from_user_id === userId || p.to_user_id === userId);
}

function PairRow({
  pair,
  meId,
  nameOf,
}: {
  pair: PairBalance;
  meId: string;
  nameOf: (id: string) => string;
}) {
  const iOwe = pair.from_user_id === meId;
  const other = iOwe ? pair.to_user_id : pair.from_user_id;
  return (
    <div className="flex items-center justify-between py-1.5 text-sm">
      <span className="text-slate-600 dark:text-slate-300">
        {iOwe ? `You owe ${nameOf(other)}` : `${nameOf(other)} owes you`}
      </span>
      <Money
        amount={pair.amount}
        className={`font-semibold ${iOwe ? "text-rose-600" : "text-emerald-600"}`}
      />
    </div>
  );
}

export function DashboardPage() {
  const { user } = useAuth();
  const { nameOf } = useUsers();
  const navigate = useNavigate();
  const [balances, setBalances] = useState<GlobalBalances | null>(null);
  const [suggestions, setSuggestions] = useState<PairBalance[]>([]);
  const [settlements, setSettlements] = useState<Settlement[]>([]);
  const [refunds, setRefunds] = useState<Refund[]>([]);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const [bal, sugg, stls, rfds, exps, grps] = await Promise.all([
        api.getGlobalBalances(),
        api.getSettlementSuggestions(),
        api.listSettlements(),
        api.listRefunds(),
        api.listExpenses({ limit: 5 }),
        api.listGroups(),
      ]);
      setBalances(bal);
      setSuggestions(sugg);
      setSettlements(stls);
      setRefunds(rfds);
      setExpenses(exps.items);
      setGroups(grps);
      setLoading(false);
    }
    load();
  }, []);

  const meId = user!.id;

  const myPendingSettlements = useMemo(
    () =>
      settlements.filter(
        (s) =>
          (s.payer_id === meId || s.recipient_id === meId) &&
          (s.status === "pending" || s.status === "reversal_pending"),
      ),
    [settlements, meId],
  );
  const myPendingRefunds = useMemo(
    () => refunds.filter((r) => r.status === "pending" && r.participant_ids.includes(meId)),
    [refunds, meId],
  );

  if (loading || !balances) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    );
  }

  const currentPairs = pairsInvolving(balances.current.pairs, meId);
  const confirmedPairs = pairsInvolving(balances.confirmed.pairs, meId);
  const mySuggestions = pairsInvolving(suggestions, meId);

  return (
    <div className="space-y-6">
      <PageHeader title={`Welcome back, ${user!.display_name}`} subtitle="Here's where things stand." />

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <div className="mb-2 flex items-center gap-2">
            <h2 className="font-semibold text-slate-800 dark:text-white">Current balance</h2>
            <Badge tone="info">includes pending settlements</Badge>
          </div>
          {currentPairs.length === 0 ? (
            <p className="text-sm text-slate-400">You're all settled up right now.</p>
          ) : (
            <div className="divide-y divide-slate-100 dark:divide-slate-700">
              {currentPairs.map((p) => (
                <PairRow key={`${p.from_user_id}-${p.to_user_id}`} pair={p} meId={meId} nameOf={nameOf} />
              ))}
            </div>
          )}
        </Card>

        <Card>
          <div className="mb-2 flex items-center gap-2">
            <h2 className="font-semibold text-slate-800 dark:text-white">Confirmed balance</h2>
            <Badge tone="neutral">excludes pending settlements</Badge>
          </div>
          {confirmedPairs.length === 0 ? (
            <p className="text-sm text-slate-400">Nothing confirmed outstanding.</p>
          ) : (
            <div className="divide-y divide-slate-100 dark:divide-slate-700">
              {confirmedPairs.map((p) => (
                <PairRow key={`${p.from_user_id}-${p.to_user_id}`} pair={p} meId={meId} nameOf={nameOf} />
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card>
        <h2 className="mb-2 font-semibold text-slate-800 dark:text-white">Suggested settlements</h2>
        {mySuggestions.length === 0 ? (
          <p className="text-sm text-slate-400">No suggestions right now — you're squared away.</p>
        ) : (
          <ul className="space-y-2">
            {mySuggestions.map((s) => {
              const iOwe = s.from_user_id === meId;
              const other = iOwe ? s.to_user_id : s.from_user_id;
              return (
                <li
                  key={`${s.from_user_id}-${s.to_user_id}`}
                  className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-700/50"
                >
                  <span className="text-sm text-slate-600 dark:text-slate-300">
                    {iOwe ? `Pay ${nameOf(other)}` : `${nameOf(other)} should pay you`}{" "}
                    <Money amount={s.amount} className="font-semibold" />
                  </span>
                  {iOwe && (
                    <Button
                      onClick={() =>
                        navigate(`/settlements?payer=${meId}&recipient=${other}&amount=${s.amount}`)
                      }
                    >
                      Settle up
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <h2 className="mb-2 font-semibold text-slate-800 dark:text-white">Pending settlements</h2>
          {myPendingSettlements.length === 0 ? (
            <p className="text-sm text-slate-400">Nothing pending.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {myPendingSettlements.map((s) => (
                <li key={s.id} className="flex items-center justify-between">
                  <span>
                    {nameOf(s.payer_id)} → {nameOf(s.recipient_id)} <Money amount={s.amount} />
                  </span>
                  <Badge tone={s.status === "reversal_pending" ? "warning" : "info"}>{s.status}</Badge>
                </li>
              ))}
            </ul>
          )}
          <Link
            to="/settlements"
            className="mt-3 inline-block text-sm text-teal-600 hover:underline dark:text-teal-400"
          >
            View all settlements →
          </Link>
        </Card>

        <Card>
          <h2 className="mb-2 font-semibold text-slate-800 dark:text-white">Pending refunds</h2>
          {myPendingRefunds.length === 0 ? (
            <p className="text-sm text-slate-400">Nothing pending.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {myPendingRefunds.map((r) => (
                <li key={r.id} className="flex items-center justify-between">
                  <span>
                    {r.title} <Money amount={r.amount} />
                  </span>
                  <Badge tone="warning">
                    {r.confirmations.filter((c) => c.confirmed).length}/{r.confirmations.length} confirmed
                  </Badge>
                </li>
              ))}
            </ul>
          )}
          <Link
            to="/refunds"
            className="mt-3 inline-block text-sm text-teal-600 hover:underline dark:text-teal-400"
          >
            View all refunds →
          </Link>
        </Card>
      </div>

      <Card>
        <h2 className="mb-2 font-semibold text-slate-800 dark:text-white">Recent expenses</h2>
        {expenses.length === 0 ? (
          <EmptyState title="No expenses yet" hint="Add one from a group page." />
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-700">
            {expenses.map((e) => (
              <li key={e.id} className="flex items-center justify-between py-2 text-sm">
                <Link to={`/expenses/${e.id}`} className="text-slate-700 hover:underline dark:text-slate-200">
                  {e.title}
                </Link>
                <span className="flex items-center gap-3">
                  <span className="text-xs text-slate-400">{e.expense_date}</span>
                  <Money amount={e.amount} className="font-medium" />
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <h2 className="mb-2 font-semibold text-slate-800 dark:text-white">Your groups</h2>
        {groups.length === 0 ? (
          <EmptyState title="No groups yet" hint="Ask your admin to add you to a group." />
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            {groups.map((g) => (
              <Link
                key={g.id}
                to={`/groups/${g.id}`}
                className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm hover:border-teal-400 dark:border-slate-700"
              >
                <span>{g.name}</span>
                {g.status === "archived" && <Badge tone="neutral">archived</Badge>}
              </Link>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
