/** UI languages. Add one by dropping messages/<locale>.json and listing it here. */
export const locales = ["en", "es", "fr", "pt", "ar", "hi", "ur", "id"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "en";
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

export function isLocale(value: string | undefined): value is Locale {
  return !!value && (locales as readonly string[]).includes(value);
}
