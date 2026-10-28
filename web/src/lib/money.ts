/**
 * Money for people to read, same rules as the API's format_amount (escalate/i18n/formatting.py):
 * the locale's own symbol and spacing, no decimals for whole amounts, the currency's digits
 * otherwise, spaces as U+00A0. Both are tested against schema/money_format_cases.json.
 * The locale is always passed explicitly, so server and browser render identical strings.
 */
const SPACES = /[\s  ]+/g;

export function formatMoney(
  amount: string | number | null | undefined,
  currency: string | null | undefined,
  locale: string,
): string | null {
  if (amount === null || amount === undefined || amount === "") return null;
  const value = typeof amount === "number" ? amount : Number(String(amount).replace(/,/g, ""));
  if (!Number.isFinite(value)) return String(amount);
  if (!currency) return new Intl.NumberFormat(locale, { maximumFractionDigits: 20 }).format(value).replace(SPACES, " ");
  try {
    const digits = new Intl.NumberFormat(locale, { style: "currency", currency }).resolvedOptions().maximumFractionDigits ?? 2;
    const shown = Number.isInteger(value) ? 0 : digits;
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency,
      minimumFractionDigits: shown,
      maximumFractionDigits: shown,
    })
      .format(value)
      .replace(SPACES, " ");
  } catch {
    return `${currency} ${value}`;
  }
}
