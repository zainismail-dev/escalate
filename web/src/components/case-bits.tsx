"use client";
import { Globe2, MapPin } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import { countryName, flag, languageName } from "@/lib/format";
import { useLetterLanguages } from "@/lib/letter-languages";
import type { CaseStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Country · currency (· letter language, when more than one is enabled): on every case. */
export function CaseChip({
  country,
  region,
  currency,
  language,
  className,
}: {
  country: string | null;
  region?: string | null;
  currency: string | null;
  language?: string;
  className?: string;
}) {
  const ui = useLocale();
  const t = useTranslations("chip");
  const showLanguage = useLetterLanguages().length > 1 && !!language;
  return (
    <span
      className={cn("inline-flex flex-wrap items-center gap-x-1.5 gap-y-0.5 rounded-full border border-line bg-card px-2.5 py-1 text-xs text-text-2", className)}
      data-testid="case-chip"
    >
      <span aria-hidden>{flag(country)}</span>
      <span className="font-semibold text-text">{countryName(country, ui) ?? t("anyCountry")}</span>
      {region && <span className="font-mono text-[0.6875rem] text-muted">{region}</span>}
      <span aria-hidden className="text-muted">·</span>
      <span className="font-mono text-[0.6875rem]">
        <span className="sr-only">{t("currency")} </span>
        {currency ?? "—"}
      </span>
      {showLanguage && (
        <>
          <span aria-hidden className="text-muted">·</span>
          <span>
            <span className="sr-only">{t("letterLanguage")} </span>
            {languageName(language, ui)}
          </span>
        </>
      )}
    </span>
  );
}

/** "Local pack" only when a country playbook exists; never implies coverage that doesn't. */
export function PackBadge({ generic, className }: { generic: boolean; className?: string }) {
  const t = useTranslations("pack");
  return generic ? (
    <Badge tone="warning" className={className} title={t("genericHint")}>
      <Globe2 aria-hidden />
      {t("generic")}
    </Badge>
  ) : (
    <Badge tone="success" className={className} title={t("localHint")}>
      <MapPin aria-hidden />
      {t("local")}
    </Badge>
  );
}

const STATUS_TONE: Record<CaseStatus, "neutral" | "lime" | "success" | "warning" | "danger" | "info"> = {
  intake: "info",
  urgent_checklist: "danger",
  drafting: "info",
  awaiting_approval: "lime",
  waiting_reply: "neutral",
  pick_next: "info",
  resolved: "success",
  closed_unresolved: "warning",
  withdrawn: "neutral",
};

export function StatusBadge({ status }: { status: CaseStatus }) {
  const t = useTranslations("status");
  return <Badge tone={STATUS_TONE[status] ?? "neutral"}>{t(status)}</Badge>;
}
