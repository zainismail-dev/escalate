"use client";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { CaseChip, PackBadge, StatusBadge } from "@/components/case-bits";
import { caseLocale, formatMoney } from "@/lib/format";
import type { CaseDetail } from "@/lib/types";

export function CaseHeader({ c, back, title }: { c: CaseDetail; back?: { href: string; label: string }; title?: string }) {
  const t = useTranslations("caseType");
  const money = formatMoney(c.amount, c.currency, caseLocale(c.language, c.country));
  return (
    <div className="space-y-3">
      {back && (
        <Link href={back.href} className="inline-flex items-center gap-1 text-sm font-semibold text-text-2 hover:text-text">
          <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden />
          {back.label}
        </Link>
      )}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="label-mono text-muted">
            #{c.id} · {t(c.case_type ?? "unknown")}
          </p>
          <h1 className="mt-1 font-display text-3xl leading-tight">{title ?? c.company ?? t(c.case_type ?? "unknown")}</h1>
        </div>
        {money && (
          <p className="font-mono text-2xl font-bold" dir="ltr" data-testid="case-amount">
            {money}
          </p>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <CaseChip country={c.country} region={c.region} currency={c.currency} language={c.language} />
        <StatusBadge status={c.status} />
        {c.playbook_id && <PackBadge generic={c.generic_playbook} />}
      </div>
    </div>
  );
}
