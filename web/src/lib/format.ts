/**
 * Locale-aware formatting with Intl. Nothing here knows a country, currency or date format:
 * a case's locale is its letter language plus its country (BCP-47), e.g. en + PK -> en-PK.
 */

export function caseLocale(language: string | null | undefined, country: string | null | undefined): string {
  const tag = (language || "en").replace("_", "-");
  const candidate = tag.includes("-") || !country ? tag : `${tag}-${country}`;
  try {
    return Intl.getCanonicalLocales(candidate)[0];
  } catch {
    return "en";
  }
}

export { formatMoney } from "./money";

export { formatDate, formatDateTime, formatLocalDateTime } from "./datetime";

const displayNames = new Map<string, Intl.DisplayNames>();

function names(locale: string, type: "region" | "language" | "currency") {
  const key = `${locale}|${type}`;
  let dn = displayNames.get(key);
  if (!dn) {
    dn = new Intl.DisplayNames([locale, "en"], { type, fallback: "code" });
    displayNames.set(key, dn);
  }
  return dn;
}

export function countryName(code: string | null | undefined, uiLocale: string) {
  if (!code) return null;
  try {
    return names(uiLocale, "region").of(code.toUpperCase()) ?? code;
  } catch {
    return code;
  }
}

export function languageName(tag: string | null | undefined, uiLocale: string) {
  if (!tag) return null;
  try {
    return names(uiLocale, "language").of(tag) ?? tag;
  } catch {
    return tag;
  }
}

export function currencyName(code: string | null | undefined, uiLocale: string) {
  if (!code) return null;
  try {
    return names(uiLocale, "currency").of(code) ?? code;
  } catch {
    return code;
  }
}

/** Regional-indicator flag emoji from an ISO 3166-1 code (purely decorative). */
export function flag(code: string | null | undefined) {
  if (!code || !/^[A-Za-z]{2}$/.test(code)) return "🌐";
  return String.fromCodePoint(...[...code.toUpperCase()].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65));
}

/** Languages a letter can be written in: the ones Intl knows how to name, by BCP-47 tag. */
export const LETTER_LANGUAGES = [
  "en", "ar", "bn", "de", "es", "fa", "fr", "he", "hi", "id", "it", "ja", "ko", "ms", "nl", "pa",
  "pl", "pt", "ru", "sw", "ta", "th", "tl", "tr", "uk", "ur", "vi", "zh",
];
