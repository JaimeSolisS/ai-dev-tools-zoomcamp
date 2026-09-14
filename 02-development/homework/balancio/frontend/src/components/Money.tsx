import { formatMoney } from "../utils/money";
import { APP_CURRENCY } from "../config";

export function Money({ amount, className = "" }: { amount: string | number; className?: string }) {
  return <span className={className}>{formatMoney(amount, APP_CURRENCY)}</span>;
}
