"use client";
import { useLocale, useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { countryName, flag } from "@/lib/format";
import { useApi } from "@/lib/use-api";

/** Which countries have a local pack today, read from the API (never hard-coded). */
export function LocalPacks() {
  const t = useTranslations("landing.global");
  const ui = useLocale();
  const { data } = useApi(() => api.countries(), []);
  if (!data) return <p className="text-sm text-muted">{t("packsLoading")}</p>;
  const local = data.filter((c) => c.local_pack);
  return (
    <div>
      <p className="text-sm text-text-2">{t("packsCount", { all: data.length, local: local.length })}</p>
      <ul className="mt-3 flex flex-wrap gap-2">
        {local.map((c) => (
          <li key={c.code} className="rounded-full border border-line bg-card px-3 py-1 text-sm">
            <span aria-hidden>{flag(c.code)}</span> {countryName(c.code, ui)}
          </li>
        ))}
        <li className="rounded-full border border-dashed border-line px-3 py-1 text-sm text-muted">{t("everyoneElse")}</li>
      </ul>
    </div>
  );
}
