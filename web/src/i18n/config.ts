/** UI languages with a messages/<locale>.json file. Add one by dropping its file and listing it. */
export const locales = ["en", "es", "fr", "pt", "ar", "hi", "ur", "id"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "en";

/**
 * Which UI languages are switched on. v0.1 ships English-only; re-enable others with
 * NEXT_PUBLIC_ENABLED_LOCALES=en,ar,... at build time (no code change). The language selector
 * only appears when more than one is enabled.
 */
export const ENABLED_LOCALES: Locale[] = (process.env.NEXT_PUBLIC_ENABLED_LOCALES || "en")
  .split(",")
  .map((s) => s.trim())
  .filter((s): s is Locale => (locales as readonly string[]).includes(s));
if (ENABLED_LOCALES.length === 0) ENABLED_LOCALES.push(defaultLocale);
export const LOCALE_COOKIE = "NEXT_LOCALE";

/** Right-to-left scripts, for the UI and for letter previews (by primary language subtag). */
export const RTL_LANGUAGES = new Set(["ar", "fa", "he", "ur", "ps", "sd", "ug", "yi", "dv", "ckb"]);

export function primaryLanguage(tag: string | null | undefined): string {
  return (tag || "en").replace("_", "-").split("-")[0].toLowerCase();
}

export function isRtl(tag: string | null | undefined): boolean {
  return RTL_LANGUAGES.has(primaryLanguage(tag));
}

export function dirFor(tag: string | null | undefined): "rtl" | "ltr" {
  return isRtl(tag) ? "rtl" : "ltr";
}

/** An enabled UI locale. */
export function isLocale(value: string | undefined): value is Locale {
  return !!value && (ENABLED_LOCALES as readonly string[]).includes(value);
}
