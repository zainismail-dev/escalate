"use client";
import { Check, ChevronRight, Pencil, X } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { CaseChip, PackBadge, StatusBadge } from "@/components/case-bits";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import type { CaseDetail } from "@/lib/types";

/** Breadcrumb "My cases › <case title>" (the last part links to the case unless we are on it). */
export function CaseBreadcrumb({ c, onCase }: { c: CaseDetail; onCase?: boolean }) {
  const t = useTranslations("dashboard");
  return (
    <nav aria-label={t("breadcrumb")} className="flex min-w-0 items-center gap-1 text-sm font-semibold text-text-2">
      <Link href="/cases" className="shrink-0 hover:text-text">
        {t("back")}
      </Link>
      <ChevronRight className="size-4 shrink-0 text-muted rtl:rotate-180" aria-hidden />
      {onCase ? (
        <span aria-current="page" className="truncate text-text">
          {c.title}
        </span>
      ) : (
        <Link href={`/cases/${c.id}`} className="truncate hover:text-text">
          {c.title}
        </Link>
      )}
    </nav>
  );
}

function TitleEditor({ c, onRenamed }: { c: CaseDetail; onRenamed: (c: CaseDetail) => void }) {
  const t = useTranslations("dashboard");
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(c.title);
  const [busy, setBusy] = useState(false);
  if (!editing) {
    return (
      <div className="flex min-w-0 items-start gap-2">
        <h1 className="min-w-0 font-display text-3xl leading-tight" data-testid="case-title">
          {c.title}
        </h1>
        <Button variant="ghost" size="icon" className="mt-0.5 size-8 shrink-0" aria-label={t("rename")} onClick={() => setEditing(true)}>
          <Pencil aria-hidden />
        </Button>
      </div>
    );
  }
  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!value.trim()) return;
        setBusy(true);
        try {
          onRenamed(await api.renameCase(c.id, value));
          setEditing(false);
        } finally {
          setBusy(false);
        }
      }}
    >
      <label htmlFor="case-title-input" className="sr-only">
        {t("titleLabel")}
      </label>
      <Input id="case-title-input" value={value} maxLength={120} onChange={(e) => setValue(e.target.value)} className="h-11 max-w-xl flex-1 text-lg font-semibold" autoFocus />
      <Button type="submit" variant="ink" size="icon" disabled={busy || !value.trim()} aria-label={t("saveTitle")}>
        <Check aria-hidden />
      </Button>
      <Button variant="ghost" size="icon" aria-label={t("cancelRename")} onClick={() => (setValue(c.title), setEditing(false))}>
        <X aria-hidden />
      </Button>
    </form>
  );
}

/**
 * Case header: breadcrumb, title (renamable on the dashboard), company underneath, amount and
 * chips. Sub-pages pass `heading` (e.g. "Review: legal notice") and keep the title in the crumb.
 */
export function CaseHeader({
  c,
  heading,
  onRenamed,
}: {
  c: CaseDetail;
  heading?: string;
  onRenamed?: (c: CaseDetail) => void;
}) {
  const t = useTranslations("caseType");
  const money = c.amount_display;
  return (
    <div className="space-y-3">
      <CaseBreadcrumb c={c} onCase={!heading} />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="label-mono text-muted">
            #{c.id} · {t(c.case_type ?? "unknown")}
          </p>
          {heading ? (
            <h1 className="mt-1 font-display text-3xl leading-tight">{heading}</h1>
          ) : onRenamed ? (
            <div className="mt-1">
              <TitleEditor key={c.title} c={c} onRenamed={onRenamed} />
            </div>
          ) : (
            <h1 className="mt-1 font-display text-3xl leading-tight">{c.title}</h1>
          )}
          {!heading && c.company && <p className="mt-1 text-text-2" data-testid="case-company">{c.company}</p>}
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
