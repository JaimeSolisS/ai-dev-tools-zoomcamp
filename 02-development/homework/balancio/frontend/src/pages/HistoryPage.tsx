import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import * as api from "../api/client";
import type { Expense, Group, Refund, Settlement } from "../types";
import { useUsers } from "../contexts/UsersContext";
import { Badge, Card, EmptyState, Input, PageHeader, Select, Spinner } from "../components/ui";
import { Money } from "../components/Money";

type HistoryItem =
  | { kind: "expense"; id: string; date: string; label: string; amount: string; extra: string }
  | { kind: "settlement"; id: string; date: string; label: string; amount: string; extra: string }
  | { kind: "refund"; id: string; date: string; label: string; amount: string; extra: string };

export function HistoryPage() {
  const { nameOf } = useUsers();
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [settlements, setSettlements] = useState<Settlement[]>([]);
  const [refunds, setRefunds] = useState<Refund[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");

  useEffect(() => {
    async function load() {
      const [exps, stls, rfds, grps] = await Promise.all([
        api.listExpenses({ limit: 500 }),
        api.listSettlements(),
        api.listRefunds(),
        api.listGroups(),
      ]);
      setExpenses(exps.items);
      setSettlements(stls);
      setRefunds(rfds);
      setGroups(grps);
      setLoading(false);
    }
    load();
  }, []);

  const groupName = (id: string) => groups.find((g) => g.id === id)?.name ?? "Unknown group";

  const items: HistoryItem[] = useMemo(() => {
    const result: HistoryItem[] = [];
    for (const e of expenses) {
      result.push({
        kind: "expense",
        id: e.id,
        date: e.expense_date,
        label: e.title,
        amount: e.amount,
        extra: groupName(e.group_id),
      });
    }
    for (const s of settlements.filter((s) => s.status === "confirmed" || s.status === "reversed")) {
      result.push({
        kind: "settlement",
        id: s.id,
        date: s.updated_at.slice(0, 10),
        label: `${nameOf(s.payer_id)} → ${nameOf(s.recipient_id)}`,
        amount: s.amount,
        extra: s.status,
      });
    }
    for (const r of refunds.filter((r) => r.status === "confirmed")) {
      result.push({
        kind: "refund",
        id: r.id,
        date: r.updated_at.slice(0, 10),
        label: r.title,
        amount: r.amount,
        extra: groupName(r.group_id),
      });
    }
    return result
      .filter((i) => !typeFilter || i.kind === typeFilter)
      .filter((i) => !search || i.label.toLowerCase().includes(search.toLowerCase()))
      .sort((a, b) => (a.date < b.date ? 1 : -1));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expenses, settlements, refunds, groups, search, typeFilter]);

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader title="History" subtitle="Every settled transaction, searchable at any time." />

      <Card>
        <div className="mb-4 flex flex-wrap gap-2">
          <Input
            placeholder="Search…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-48"
          />
          <Select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="w-48">
            <option value="">All types</option>
            <option value="expense">Expenses</option>
            <option value="settlement">Settlements</option>
            <option value="refund">Refunds</option>
          </Select>
        </div>

        {items.length === 0 ? (
          <EmptyState title="Nothing to show" hint="Try a different search or filter." />
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-700">
            {items.map((i) => (
              <li key={`${i.kind}-${i.id}`} className="flex items-center justify-between py-2 text-sm">
                <div>
                  {i.kind === "expense" ? (
                    <Link
                      to={`/expenses/${i.id}`}
                      className="font-medium text-slate-700 hover:underline dark:text-slate-200"
                    >
                      {i.label}
                    </Link>
                  ) : (
                    <span className="font-medium text-slate-700 dark:text-slate-200">{i.label}</span>
                  )}
                  <p className="text-xs text-slate-400">
                    {i.date} · {i.extra}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge
                    tone={i.kind === "expense" ? "info" : i.kind === "settlement" ? "success" : "warning"}
                  >
                    {i.kind}
                  </Badge>
                  <Money amount={i.amount} className="font-medium" />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
