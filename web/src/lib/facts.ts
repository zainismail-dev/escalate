import { formatDate, formatMoney } from "./format";

const ISO_DATE = /^\d{4}-\d{2}-\d{2}/;

/** Show a fact the way the case's locale writes it (money, dates); everything else as typed. */
export function displayFact(key: string, value: string, currency: string | null, locale: string): string {
  if (key === "amount") return formatMoney(value, currency, locale) ?? value;
  if (ISO_DATE.test(value)) return formatDate(value, locale, "long") ?? value;
  return value;
}

export function inputTypeFor(key: string): "date" | "email" | "text" {
  if (/(_on|_date)$/.test(key)) return "date";
  return "text";
}
