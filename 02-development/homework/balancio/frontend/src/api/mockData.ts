import type { Db } from "./db";
import type { Expense, Refund, Settlement } from "../types";
import { toCents, splitEqually, fromCents } from "../utils/money";
import { newId } from "../utils/id";

function equalShares(amount: string, participantIds: string[]) {
  const cents = splitEqually(toCents(amount), participantIds);
  return participantIds.map((user_id) => ({
    user_id,
    amount: fromCents(cents.get(user_id) ?? 0),
  }));
}

const now = new Date().toISOString();

export const DEMO_CREDENTIALS = [
  { username: "admin", password: "admin1234", note: "Global admin" },
  { username: "jaime", password: "jaime1234", note: "Regular user" },
  { username: "ana", password: "ana1234", note: "Regular user" },
  { username: "carlos", password: "carlos1234", note: "Regular user" },
  { username: "sofia", password: "sofia1234", note: "Regular user" },
  { username: "sam", password: "temp1234", note: "Must change password on login" },
];

export function buildSeedDb(): Db {
  const u = {
    admin: newId("usr"),
    jaime: newId("usr"),
    ana: newId("usr"),
    carlos: newId("usr"),
    sofia: newId("usr"),
    sam: newId("usr"),
  };

  const db: Db = {
    users: [
      {
        id: u.admin,
        username: "admin",
        display_name: "Admin",
        role: "admin",
        is_active: true,
        must_change_password: false,
        theme: "light",
        created_at: now,
        updated_at: now,
      },
      {
        id: u.jaime,
        username: "jaime",
        display_name: "Jaime",
        role: "user",
        is_active: true,
        must_change_password: false,
        theme: "light",
        created_at: now,
        updated_at: now,
      },
      {
        id: u.ana,
        username: "ana",
        display_name: "Ana",
        role: "user",
        is_active: true,
        must_change_password: false,
        theme: "light",
        created_at: now,
        updated_at: now,
      },
      {
        id: u.carlos,
        username: "carlos",
        display_name: "Carlos",
        role: "user",
        is_active: true,
        must_change_password: false,
        theme: "light",
        created_at: now,
        updated_at: now,
      },
      {
        id: u.sofia,
        username: "sofia",
        display_name: "Sofia",
        role: "user",
        is_active: true,
        must_change_password: false,
        theme: "light",
        created_at: now,
        updated_at: now,
      },
      {
        id: u.sam,
        username: "sam",
        display_name: "Sam",
        role: "user",
        is_active: true,
        must_change_password: true,
        theme: "light",
        created_at: now,
        updated_at: now,
      },
    ],
    passwords: {
      [u.admin]: "admin1234",
      [u.jaime]: "jaime1234",
      [u.ana]: "ana1234",
      [u.carlos]: "carlos1234",
      [u.sofia]: "sofia1234",
      [u.sam]: "temp1234",
    },
    groups: [],
    categories: [],
    expenses: [],
    settlements: [],
    refunds: [],
    comments: [],
  };

  const globalCategoryNames = [
    "Groceries",
    "Rent",
    "Utilities",
    "Dining",
    "Travel",
    "Entertainment",
    "Transportation",
    "Other",
  ];
  const categories = Object.fromEntries(
    globalCategoryNames.map((name) => [name, { id: newId("cat"), name, group_id: null, created_at: now }]),
  );
  db.categories.push(...Object.values(categories));

  const homeId = newId("grp");
  const tripId = newId("grp");
  const pokerId = newId("grp");
  const oldTripId = newId("grp");

  db.groups.push(
    {
      id: homeId,
      name: "Home",
      description: "Shared apartment expenses",
      member_ids: [u.jaime, u.ana],
      status: "active",
      created_at: now,
      updated_at: now,
    },
    {
      id: tripId,
      name: "Trip",
      description: "Weekend trip to the coast",
      member_ids: [u.jaime, u.ana, u.carlos, u.sofia],
      status: "active",
      created_at: now,
      updated_at: now,
    },
    {
      id: pokerId,
      name: "Poker Night",
      description: "Monthly poker night",
      member_ids: [u.jaime, u.ana, u.carlos],
      status: "active",
      created_at: now,
      updated_at: now,
    },
    {
      id: oldTripId,
      name: "Old Ski Trip",
      description: "Settled up already",
      member_ids: [u.jaime, u.ana],
      status: "archived",
      created_at: now,
      updated_at: now,
    },
  );

  const souvenirsCategory = { id: newId("cat"), name: "Souvenirs", group_id: tripId, created_at: now };
  db.categories.push(souvenirsCategory);

  function makeExpense(partial: {
    group_id: string;
    title: string;
    amount: string;
    category_id: string | null;
    created_by: string;
    payers: { user_id: string; amount: string }[];
    participant_ids: string[];
    tags?: string[];
    note?: string;
    expense_date: string;
  }): Expense {
    return {
      id: newId("exp"),
      group_id: partial.group_id,
      title: partial.title,
      amount: partial.amount,
      expense_date: partial.expense_date,
      category_id: partial.category_id,
      note: partial.note,
      tags: partial.tags ?? [],
      created_by: partial.created_by,
      payers: partial.payers,
      participant_ids: partial.participant_ids,
      shares: equalShares(partial.amount, partial.participant_ids),
      created_at: now,
      updated_at: now,
    };
  }

  db.expenses.push(
    makeExpense({
      group_id: homeId,
      title: "Rent",
      amount: "600.00",
      category_id: categories.Rent.id,
      created_by: u.ana,
      payers: [{ user_id: u.ana, amount: "600.00" }],
      participant_ids: [u.ana, u.jaime],
      expense_date: "2026-09-01",
      tags: ["fixed"],
    }),
    makeExpense({
      group_id: tripId,
      title: "Hotel",
      amount: "300.00",
      category_id: categories.Travel.id,
      created_by: u.jaime,
      payers: [{ user_id: u.jaime, amount: "300.00" }],
      participant_ids: [u.jaime, u.ana],
      expense_date: "2026-09-05",
      tags: ["vacation"],
    }),
    makeExpense({
      group_id: tripId,
      title: "Souvenirs",
      amount: "60.00",
      category_id: souvenirsCategory.id,
      created_by: u.carlos,
      payers: [{ user_id: u.carlos, amount: "60.00" }],
      participant_ids: [u.carlos, u.sofia],
      expense_date: "2026-09-06",
      tags: ["vacation"],
    }),
    makeExpense({
      group_id: pokerId,
      title: "Snacks",
      amount: "40.00",
      category_id: categories.Groceries.id,
      created_by: u.jaime,
      payers: [{ user_id: u.jaime, amount: "40.00" }],
      participant_ids: [u.jaime, u.ana],
      expense_date: "2026-09-08",
    }),
    makeExpense({
      group_id: pokerId,
      title: "Cab ride",
      amount: "40.00",
      category_id: categories.Transportation.id,
      created_by: u.carlos,
      payers: [{ user_id: u.carlos, amount: "40.00" }],
      participant_ids: [u.carlos, u.jaime],
      expense_date: "2026-09-08",
    }),
  );

  const settlement1: Settlement = {
    id: newId("stl"),
    payer_id: u.jaime,
    recipient_id: u.ana,
    amount: "100.00",
    note: "Partial payment for rent",
    status: "pending",
    created_at: now,
    updated_at: now,
  };
  const settlement2: Settlement = {
    id: newId("stl"),
    payer_id: u.sofia,
    recipient_id: u.carlos,
    amount: "30.00",
    note: "Souvenirs settled",
    status: "confirmed",
    created_at: now,
    updated_at: now,
  };
  db.settlements.push(settlement1, settlement2);

  const refund1: Refund = {
    id: newId("rfd"),
    group_id: tripId,
    title: "Returned bus tickets",
    amount: "40.00",
    participant_ids: [u.ana, u.jaime],
    created_by: u.ana,
    status: "pending",
    confirmations: [
      { user_id: u.ana, confirmed: true },
      { user_id: u.jaime, confirmed: false },
    ],
    created_at: now,
    updated_at: now,
  };
  db.refunds.push(refund1);

  db.comments.push({
    id: newId("cmt"),
    transaction_type: "expense",
    transaction_id: db.expenses[0].id,
    author_id: u.jaime,
    body: "Thanks for covering this one, I'll get the next one!",
    created_at: now,
    updated_at: now,
  });

  return db;
}
