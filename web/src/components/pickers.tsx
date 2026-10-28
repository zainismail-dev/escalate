"use client";
import { Search } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useId, useMemo, useState } from "react";
import { PackBadge } from "@/components/case-bits";
import { FieldHint, Input, Label, NativeSelect } from "@/components/ui/input";
import { countryName, currencyName, flag, languageName, LETTER_LANGUAGES } from "@/lib/format";
import type { Country } from "@/lib/types";

/** All countries (from the API), named in the UI language. Badge says if a local pack exists. */
export function CountryPicker({
  countries,
  value,
  onChange,
  caseType,
}: {
  countries: Country[];
  value: string;
  onChange: (code: string) => void;
  caseType?: string | null;
}) {
  const t = useTranslations("picker");
  const ui = useLocale();
  const id = useId();
  const [q, setQ] = useState("");
  const rows = useMemo(() => {
    const named = countries.map((c) => ({ ...c, name: countryName(c.code, ui) ?? c.code }));
    named.sort((a, b) => a.name.localeCompare(b.name, ui));
    const needle = q.trim().toLocaleLowerCase(ui);
    return needle ? named.filter((c) => c.name.toLocaleLowerCase(ui).includes(needle) || c.code.toLowerCase() === needle) : named;
  }, [countries, q, ui]);
  const selected = countries.find((c) => c.code === value);
  const local = selected ? (caseType ? !!selected.packs[caseType] : selected.local_pack) : false;
  return (
    <div className="space-y-2">
      <Label htmlFor={`${id}-select`}>{t("country")}</Label>
      <div className="relative">
        <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
        <Input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("search")}
          aria-label={t("search")}
          aria-controls={`${id}-select`}
          className="ps-9"
        />
      </div>
      <NativeSelect
        id={`${id}-select`}
        size={7}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-auto py-1"
        data-testid="country-select"
      >
        {rows.map((c) => (
          <option key={c.code} value={c.code} className="rounded-md px-2 py-1">
            {flag(c.code)} {c.name} · {c.currency ?? "—"} · {c.local_pack ? t("localShort") : t("genericShort")}
          </option>
        ))}
      </NativeSelect>
      <FieldHint>{t("count", { count: countries.length })}</FieldHint>
      {selected && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-line bg-raised p-3 text-sm" data-testid="country-summary">
          <span aria-hidden className="text-lg">{flag(selected.code)}</span>
          <span className="font-semibold">{countryName(selected.code, ui)}</span>
          <span className="font-mono text-xs text-muted">
            {selected.currency} · {currencyName(selected.currency, ui)}
          </span>
          <PackBadge generic={!local} />
          <p className="basis-full text-xs text-text-2">{local ? t("localExplain") : t("genericExplain")}</p>
        </div>
      )}
    </div>
  );
}

/** Letter languages by BCP-47 tag, named by Intl in the UI language. */
export function LanguagePicker({
  value,
  onChange,
  label,
  available,
  id,
}: {
  value: string;
  onChange: (tag: string) => void;
  label: string;
  available?: string[];
  id?: string;
}) {
  const ui = useLocale();
  const t = useTranslations("picker");
  const gen = useId();
  const sid = id ?? gen;
  const options = useMemo(() => {
    const tags = Array.from(new Set([value, ...LETTER_LANGUAGES]));
    return tags
      .map((tag) => ({ tag, name: languageName(tag, ui) ?? tag }))
      .sort((a, b) => a.name.localeCompare(b.name, ui));
  }, [value, ui]);
  return (
    <div className="space-y-1.5">
      <Label htmlFor={sid}>{label}</Label>
      <NativeSelect id={sid} value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o.tag} value={o.tag}>
            {o.name} ({o.tag})
            {available && available.includes(o.tag.split("-")[0]) ? ` · ${t("templateReady")}` : ""}
          </option>
        ))}
      </NativeSelect>
    </div>
  );
}
