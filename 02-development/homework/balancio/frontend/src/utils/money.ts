// All monetary math is done in integer cents to avoid binary floating point
// errors, per the spec. Amounts are stored/displayed as decimal strings.

export function toCents(amount: string | number): number {
  const n = typeof amount === "number" ? amount : Number(amount);
  return Math.round(n * 100);
}

export function fromCents(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  const whole = Math.floor(abs / 100);
  const frac = abs % 100;
  return `${sign}${whole}.${frac.toString().padStart(2, "0")}`;
}

export function formatMoney(amount: string | number, currency = "MXN"): string {
  const cents = toCents(amount);
  const value = cents / 100;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    currencyDisplay: "narrowSymbol",
  }).format(value);
}

/**
 * Splits `totalCents` equally among `n` shares, assigning remainder cents
 * deterministically (in `order`) so repeated calculations are stable.
 */
export function splitEqually(totalCents: number, order: string[]): Map<string, number> {
  const n = order.length;
  const base = Math.floor(totalCents / n);
  const remainder = totalCents - base * n;
  const sorted = [...order].sort();
  const result = new Map<string, number>();
  sorted.forEach((id, i) => {
    result.set(id, base + (i < remainder ? 1 : 0));
  });
  return result;
}
