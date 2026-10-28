import { cookies, headers } from "next/headers";
import { getRequestConfig } from "next-intl/server";
import en from "../../messages/en.json";
import { defaultLocale, isLocale, LOCALE_COOKIE, type Locale, locales } from "./config";
import { loaders } from "./loaders.generated";

type Messages = Record<string, unknown>;

/** Untranslated keys fall back to English, so a half-done translation still works. */
function merge(base: Messages, over: Messages): Messages {
  const out: Messages = { ...base };
  for (const [k, v] of Object.entries(over)) {
    if (k.startsWith("_")) continue;
    const b = base[k];
    out[k] =
      v && typeof v === "object" && b && typeof b === "object"
        ? merge(b as Messages, v as Messages)
        : v;
  }
  return out;
}

function fromAcceptLanguage(header: string | null): Locale | undefined {
  for (const part of (header || "").split(",")) {
    const tag = part.split(";")[0].trim().toLowerCase().split("-")[0];
    if (isLocale(tag)) return tag;
  }
  return undefined;
}

export default getRequestConfig(async () => {
  const cookie = (await cookies()).get(LOCALE_COOKIE)?.value;
  const locale: Locale = isLocale(cookie)
    ? cookie
    : (fromAcceptLanguage((await headers()).get("accept-language")) ?? defaultLocale);
  // Only enabled, translated locales are bundled (scripts/gen-locales.mjs); others show English.
  const load = loaders[locale];
  const own = load ? ((await load()).default as Messages) : {};
  const translated = Object.keys(own).some((k) => !k.startsWith("_"));
  return {
    locale,
    messages: merge(merge(en as Messages, own), { meta: { translated: translated || locale === "en" } }),
  };
});

export { locales };
