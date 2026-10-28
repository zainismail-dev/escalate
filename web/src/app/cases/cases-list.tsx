"use client";
import { AlertTriangle, ArrowRight, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useDeferredValue, useMemo, useState } from "react";
import { CaseChip, PackBadge, StatusBadge } from "@/components/case-bits";
import { MiniLadder } from "@/components/ladder";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { caseLocale, countryName, formatDateTime, formatMoney } from "@/lib/format";
import type { CaseStatus, CaseSummary } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

const NEEDS_YOU = new Set(["approve_draft", "questions", "urgent_checklist", "confirm_delivery"]);
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
    default:
      return `/cases/${c.id}`;
  }
}

function Title({ c }: { c: CaseSummary }) {
  const t = useTranslations("caseType");
  const locale = caseLocale(c.language, c.country);
  const money = formatMoney(c.amount, c.currency, locale);
  return (
    <span className="inline-flex flex-wrap items-baseline gap-x-2">
      <span>{c.title || t(c.case_type ?? "unknown")}</span>
      {money && (
        <span className="font-mono text-sm font-semibold text-text-2" dir="ltr">
          {money}
        </span>
      )}
    </span>
  );
}

function NeedsYouCard({ c }: { c: CaseSummary }) {
  const t = useTranslations("cases");
  const tw = useTranslations("waiting");
  const urgent = c.waiting_for === "urgent_checklist";
  const kind = c.waiting_for && NEEDS_YOU.has(c.waiting_for) ? c.waiting_for : "deadline";
  return (
    <li>
      <Link
        href={actionHref(c)}
        className={cn(
          "group flex h-full flex-col gap-3 rounded-2xl border p-4 transition-colors",
          urgent ? "border-danger bg-danger-bg" : "border-line-strong bg-card hover:bg-raised",
        )}
        data-testid="needs-you-card"
      >
        <div className="flex items-center justify-between gap-2">
          <span className={cn("label-mono font-bold", urgent ? "text-danger" : "text-text")}>
            {urgent && <AlertTriangle className="me-1 inline size-3.5" aria-hidden />}
            {kind === "deadline" ? t("deadlineSoon") : tw(kind)}
          </span>
          <span className="label-mono text-muted">#{c.id}</span>
        </div>
        <p className="font-display text-lg leading-tight">
          <Title c={c} />
        </p>
        <CaseChip country={c.country} currency={c.currency} language={c.language} className="w-fit" />
        <span className="mt-auto inline-flex items-center gap-1 text-sm font-semibold">
          <span className={cn("rounded-lg px-2.5 py-1", urgent ? "bg-danger text-white dark:text-night" : "bg-lime text-on-lime")}>
            {t(`cta.${kind}`)}
          </span>
          <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5 rtl:rotate-180 rtl:group-hover:-translate-x-0.5" aria-hidden />
        </span>
      </Link>
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
  const needsYou = (all.data ?? []).filter((c) => (c.waiting_for && NEEDS_YOU.has(c.waiting_for)) || c.deadline_warning);
  const rows = filtered.data ?? [];
  const reloadAll = () => {
    void all.reload();
    void filtered.reload();
  };

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="label-mono text-muted">{t("eyebrow")}</p>
          <h1 className="mt-1 font-display text-3xl">{t("title")}</h1>
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
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="skeleton">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-40" />
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

      {needsYou.length > 0 && (
        <section aria-labelledby="needs-you">
          <h2 id="needs-you" className="font-display text-xl">
            {t("needsYou")} <span className="label-mono ms-1 rounded-md bg-lime px-1.5 py-0.5 align-middle text-on-lime">{needsYou.length}</span>
          </h2>
          <ul className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {needsYou.map((c) => (
              <NeedsYouCard key={c.id} c={c} />
            ))}
          </ul>
        </section>
      )}

      {all.data && all.data.length > 0 && (
        <section aria-labelledby="all-cases" className="space-y-3">
          <h2 id="all-cases" className="font-display text-xl">{t("all")}</h2>
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
          {filtered.data && rows.length === 0 && <p className="rounded-xl border border-dashed border-line p-6 text-center text-sm text-muted">{t("noMatch")}</p>}
          <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-card" data-testid="case-list">
            {rows.map((c) => (
              <li key={c.id}>
                <Link href={`/cases/${c.id}`} className="flex flex-wrap items-center gap-x-4 gap-y-2 p-4 hover:bg-raised">
                  <MiniLadder steps={c.ladder} label={t("ladderLabel", { step: c.step_name ?? "—" })} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold">
                      <Title c={c} />
                    </p>
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      <CaseChip country={c.country} currency={c.currency} language={c.language} />
                      {c.playbook_id && <PackBadge generic={c.generic_playbook} />}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1 text-end">
                    <StatusBadge status={c.status} />
                    <span className="label-mono text-muted">
                      {c.next_action_at ? t("nextOn", { when: formatDateTime(c.next_action_at, caseLocale(c.language, c.country)) ?? "" }) : c.step_name ?? ""}
                    </span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
