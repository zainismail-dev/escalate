"use client";
import { AlertTriangle, ArrowRight, Clock, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useDeferredValue, useMemo, useState } from "react";
import { CaseChip } from "@/components/case-bits";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { countryName } from "@/lib/format";
import type { CaseStatus, CaseSummary } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

const NEEDS_YOU = new Set(["approve_draft", "questions", "urgent_checklist", "confirm_delivery", "confirm_resolution"]);
const STATUSES: CaseStatus[] = [
  "urgent_checklist",
  "intake",
  "awaiting_approval",
  "waiting_reply",
  "resolved",
  "closed_unresolved",
  "withdrawn",
];

function actionHref(c: CaseSummary) {
  switch (c.waiting_for) {
    case "approve_draft":
      return `/cases/${c.id}/review`;
    case "questions":
      return `/cases/${c.id}/questions`;
    case "urgent_checklist":
      return `/cases/${c.id}/urgent`;
    case "confirm_resolution":
      return `/cases/${c.id}/reply`;
    default:
      return `/cases/${c.id}`;
  }
}

/** The real next step: "Approve 15-day legal notice", "Do the checklist", "Waiting for a reply". */
function useNextStep() {
  const t = useTranslations("cases.next");
  const ts = useTranslations("status");
  return (c: CaseSummary) => {
    const step = c.step_name ?? "";
    switch (c.waiting_for) {
      case "approve_draft":
        return t("approve", { step });
      case "questions":
        return t("questions");
      case "urgent_checklist":
        return t("checklist");
      case "confirm_delivery":
        return t("confirmDelivery", { step });
      case "waiting_reply":
        return t("waitingReply");
      case "confirm_resolution":
        return t("confirmResolution");
      default:
        return ts(c.status);
    }
  };
}

function CaseCard({ c }: { c: CaseSummary }) {
  const t = useTranslations("cases");
  const nextStep = useNextStep();
  const urgent = c.waiting_for === "urgent_checklist";
  const needsYou = !!c.waiting_for && NEEDS_YOU.has(c.waiting_for);
  const cta = needsYou ? t(`cta.${c.waiting_for}`) : t("cta.open");
  return (
    <li
      className={cn(
        "flex h-full flex-col gap-3 rounded-2xl border bg-card p-5",
        urgent ? "border-2 border-danger bg-danger-bg" : "border-line",
      )}
      data-testid="case-card"
      data-urgent={urgent || undefined}
    >
      <div className="flex items-center justify-between gap-2">
        <span className={cn("label-mono font-bold", urgent ? "text-danger" : needsYou ? "text-text" : "text-muted")} data-testid="next-step">
          {urgent && <AlertTriangle className="me-1 inline size-3.5 align-[-2px]" aria-hidden />}
          {nextStep(c)}
        </span>
        <span className="label-mono text-muted">#{c.id.slice(0, 8)}</span>
      </div>
      <div className="min-w-0">
        <h3 className="font-display text-xl leading-tight">
          <Link href={`/cases/${c.id}`} className="hover:underline">
            {c.title}
          </Link>
        </h3>
        {c.company && <p className="mt-0.5 text-sm text-text-2">{c.company}</p>}
        {c.amount_display && (
          <p className="mt-1 text-base font-semibold text-muted" data-testid="card-amount">
            {c.amount_display}
          </p>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <CaseChip country={c.country} currency={c.currency} />
        {c.days_left !== null && (
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold",
              c.days_left <= 3 ? "bg-danger-bg text-danger" : "bg-raised text-text-2",
            )}
            data-testid="days-left"
          >
            <Clock className="size-3.5" aria-hidden />
            {c.days_left < 0 ? t("overdue", { days: -c.days_left }) : t("daysLeft", { days: c.days_left })}
          </span>
        )}
      </div>
      <div className="mt-auto pt-1">
        <Button variant={urgent ? "danger" : needsYou ? "lime" : "outline"} asChild>
          <Link href={actionHref(c)}>
            {cta}
            <ArrowRight className="rtl:rotate-180" aria-hidden />
          </Link>
        </Button>
      </div>
    </li>
  );
}

export function CasesList() {
  const t = useTranslations("cases");
  const ts = useTranslations("status");
  const ui = useLocale();
  const [q, setQ] = useState("");
  const [country, setCountry] = useState("");
  const [status, setStatus] = useState("");
  const deferredQ = useDeferredValue(q);
  const all = useApi(() => api.listCases(), []);
  const filtered = useApi(() => api.listCases({ q: deferredQ, country, status }), [deferredQ, country, status]);

  const countries = useMemo(
    () => Array.from(new Set((all.data ?? []).map((c) => c.country).filter(Boolean) as string[])),
    [all.data],
  );
  const needsYou = (all.data ?? []).filter((c) => (c.waiting_for && NEEDS_YOU.has(c.waiting_for)) || c.deadline_warning).length;
  const rows = filtered.data ?? [];
  const reloadAll = () => {
    void all.reload();
    void filtered.reload();
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="label-mono text-muted">{t("eyebrow")}</p>
          <h1 className="mt-1 font-display text-3xl">{t("title")}</h1>
          {needsYou > 0 && (
            <p className="mt-1 text-sm text-text-2" data-testid="needs-you-count">
              {t("needsYouCount", { count: needsYou })}
            </p>
          )}
        </div>
        <Button variant="lime" asChild>
          <Link href="/cases/new">
            <Plus aria-hidden />
            {t("new")}
          </Link>
        </Button>
      </div>

      {all.error && <ErrorState error={all.error} onRetry={reloadAll} />}

      {all.loading && !all.data && (
        <div className="grid gap-4 md:grid-cols-2" data-testid="skeleton">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-56" />
          ))}
        </div>
      )}

      {all.data && all.data.length === 0 && (
        <EmptyState
          title={t("empty.title")}
          body={t("empty.body")}
          action={
            <Button variant="lime" asChild>
              <Link href="/cases/new">{t("new")}</Link>
            </Button>
          }
          onDemo={reloadAll}
        />
      )}

      {all.data && all.data.length > 0 && (
        <>
          <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto]">
            <div className="relative">
              <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
              <Input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")} aria-label={t("search")} className="ps-9" />
            </div>
            <NativeSelect value={country} onChange={(e) => setCountry(e.target.value)} aria-label={t("filterCountry")}>
              <option value="">{t("allCountries")}</option>
              {countries.map((cc) => (
                <option key={cc} value={cc}>
                  {countryName(cc, ui)}
                </option>
              ))}
            </NativeSelect>
            <NativeSelect value={status} onChange={(e) => setStatus(e.target.value)} aria-label={t("filterStatus")}>
              <option value="">{t("allStatuses")}</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {ts(s)}
                </option>
              ))}
            </NativeSelect>
          </div>
          {filtered.data && rows.length === 0 && (
            <p className="rounded-xl border border-dashed border-line p-6 text-center text-sm text-muted">{t("noMatch")}</p>
          )}
          <ul className="grid gap-4 md:grid-cols-2" data-testid="case-grid" aria-label={t("all")}>
            {rows.map((c) => (
              <CaseCard key={c.id} c={c} />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
