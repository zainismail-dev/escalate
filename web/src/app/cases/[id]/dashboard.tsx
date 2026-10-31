"use client";
import { AlertTriangle, CalendarClock, FileDown, FileText, Mail, Trash2, Undo2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { FactChip, useFactLabel } from "@/components/fact-chip";
import { EscalationLadder } from "@/components/ladder";
import { FileLink } from "@/components/hosted";
import { NextMove } from "@/components/next-move";
import { ErrorState, PageSkeleton } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/input";
import { WhyPanel } from "@/components/why-panel";
import { api } from "@/lib/api";
import { HOSTED } from "@/lib/hosted";
import { displayFact } from "@/lib/facts";
import { caseLocale, formatDate, formatDateTime } from "@/lib/format";
import type { CaseDetail } from "@/lib/types";
import { useAction, useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";
import { CaseHeader } from "./case-header";

function Deadlines({ c, locale }: { c: CaseDetail; locale: string }) {
  const t = useTranslations("dashboard");
  if (c.deadlines.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("deadlines")}</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {c.deadlines.map((d) => (
            <li
              key={d.id}
              className={cn(
                "rounded-xl border p-3 text-sm",
                d.late || d.warn ? "border-danger bg-danger-bg" : "border-line",
              )}
              data-testid="deadline"
            >
              <p className={cn("flex items-center gap-1.5 font-semibold", (d.late || d.warn) && "text-danger")}>
                {(d.late || d.warn) && <AlertTriangle className="size-4" aria-hidden />}
                {d.due ? formatDate(d.due, locale, "long") : t("dueUnknown")}
                {d.days_left !== null && (
                  <span className="label-mono ms-auto">{d.late ? t("late") : t("daysLeft", { days: d.days_left })}</span>
                )}
              </p>
              <p className="mt-1 text-xs text-text-2">{d.rule}</p>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function Timeline({ id, locale }: { id: string; locale: string }) {
  const t = useTranslations("timeline");
  const { data } = useApi(() => api.timeline(id), [id]);
  if (!data) return null;
  return (
    <ol className="relative space-y-3 border-s border-line ps-5">
      {[...data].reverse().map((e) => (
        <li key={e.id} className="relative">
          <span className="absolute -start-[1.6rem] top-1.5 size-2.5 rounded-full border-2 border-card bg-muted" aria-hidden />
          <p className="text-sm font-semibold">{t.has(e.type) ? t(e.type) : e.type.replace(/_/g, " ")}</p>
          <p className="label-mono text-muted">{formatDateTime(e.created_at, locale)}</p>
        </li>
      ))}
    </ol>
  );
}

export function CaseDashboard({ id }: { id: string }) {
  const t = useTranslations("dashboard");
  const tc = useTranslations("common");
  const ui = useLocale();
  const router = useRouter();
  const label = useFactLabel();
  const { data: c, error, loading, reload, setData } = useApi(() => api.getCase(id), [id]);
  const act = useAction();
  const [confirm, setConfirm] = useState<"withdraw" | "delete" | "delivery" | null>(null);
  const [proof, setProof] = useState<File | null>(null);

  if (loading && !c) return <PageSkeleton />;
  if (error && !c) return <ErrorState error={error} onRetry={reload} />;
  if (!c) return null;

  const locale = caseLocale(c.language, c.country);
  const files = new Map(c.evidence.map((e) => [e.id, e.filename]));
  const stalled = !c.waiting_for && ["drafting", "pick_next", "intake"].includes(c.status) && c.evidence.length > 0 && !!c.playbook_id;
  const outgoing = c.messages.filter((m) => m.direction === "out" && m.sent_at);

  async function confirmDelivery() {
    if (!c?.pending?.message_id) return;
    const msgId = c.pending.message_id;
    await act.run(async () => {
      const ev = proof ? await api.uploadEvidence(c.id, proof) : null;
      return api.confirmDelivery(msgId, ev?.id);
    });
    setConfirm(null);
    void reload();
  }

  return (
    <div className="space-y-6">
      <CaseHeader c={c} onRenamed={setData} />

      {act.error && <ErrorState error={act.error} />}
      {stalled && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-2xl border border-warning bg-warning-bg p-4 text-sm">
          <AlertTriangle className="size-5 text-warning" aria-hidden />
          <p className="flex-1 text-text-2">{t("stalled")}</p>
          <Button size="sm" variant="ink" disabled={act.busy} onClick={() => act.run(() => api.retry(c.id)).then(() => reload())}>
            {t("retry")}
          </Button>
        </div>
      )}

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>{t("ladder")}</CardTitle>
          {c.step_name && <span className="label-mono text-muted">{t("currentStep", { step: c.step_name })}</span>}
        </CardHeader>
        <CardContent>
          {c.ladder.length > 0 ? <EscalationLadder steps={c.ladder} /> : <p className="text-sm text-muted">{t("noLadder")}</p>}
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-[1.25fr_1fr]">
        <div className="space-y-6">
          <NextMove c={c} onDeliveryUpload={() => setConfirm("delivery")} onSent={() => void reload()} />
          <Deadlines c={c} locale={locale} />
          <Card>
            <CardHeader>
              <CardTitle>{t("facts")}</CardTitle>
            </CardHeader>
            <CardContent>
              {c.facts.length === 0 ? (
                <p className="text-sm text-muted">{t("noFacts")}</p>
              ) : (
                <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {c.facts.map((f) => (
                    <FactChip
                      key={f.key}
                      label={label(f.key)}
                      value={displayFact(f)}
                      source={f.source_evidence_id ? files.get(f.source_evidence_id) : null}
                    />
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
          {outgoing.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>{t("sent")}</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {outgoing.map((m) => (
                    <li key={m.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-line p-3 text-sm">
                      <Mail className="size-4 text-muted" aria-hidden />
                      <span className="min-w-0 flex-1 truncate font-semibold">{m.subject || m.step_id}</span>
                      <span className="label-mono text-muted">{formatDateTime(m.sent_at, locale)}</span>
                      <FileLink className="text-xs font-semibold text-info underline-offset-2 hover:underline" href={api.printableUrl(m.id)} hosted={HOSTED} download={() => api.downloadLetterPdf(m.id)}>
                        {t("pdf")}
                      </FileLink>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </div>
        <div className="space-y-6">
          {c.reasons.length > 0 && (
            <WhyPanel reasons={c.reasons} playbook={c.playbook_id} version={c.playbook_version} sources={c.sources} />
          )}
          <Card>
            <CardHeader>
              <CardTitle>{t("evidence")}</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {c.evidence.map((e) => (
                  <li key={e.id} className="flex items-center gap-2 text-sm">
                    <FileText className="size-4 text-muted" aria-hidden />
                    <span className="min-w-0 flex-1 truncate">{e.filename}</span>
                    <span className="label-mono text-muted">{formatDate(e.uploaded_at, locale)}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-muted">{t("encrypted")}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CalendarClock className="size-5" aria-hidden />
                {t("timeline")}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Timeline id={c.id} locale={locale} />
            </CardContent>
          </Card>
          <div className="flex flex-wrap gap-2">
            <Button asChild>
              <FileLink href={api.exportUrl(c.id)} hosted={HOSTED} download={() => api.downloadCasePdf(c.id)}>
                <FileDown aria-hidden />
                {t("export")}
              </FileLink>
            </Button>
            {!["withdrawn", "resolved"].includes(c.status) && (
              <Button variant="ghost" onClick={() => setConfirm("withdraw")}>
                <Undo2 aria-hidden />
                {t("withdraw")}
              </Button>
            )}
            <Button variant="ghost" className="text-danger" onClick={() => setConfirm("delete")}>
              <Trash2 aria-hidden />
              {t("delete")}
            </Button>
          </div>
        </div>
      </div>

      <Dialog open={confirm !== null} onOpenChange={(o) => !o && setConfirm(null)}>
        <DialogContent closeLabel={tc("close")}>
          {confirm === "delivery" ? (
            <>
              <DialogTitle>{t("delivery.title")}</DialogTitle>
              <DialogDescription>{t("delivery.body", { note: c.pending?.note ?? "" })}</DialogDescription>
              <div className="mt-4 space-y-1.5">
                <Label htmlFor="proof">{t("delivery.proof")}</Label>
                <input
                  id="proof"
                  type="file"
                  accept="image/*,application/pdf"
                  onChange={(e) => setProof(e.target.files?.[0] ?? null)}
                  className="block w-full text-sm file:me-3 file:rounded-lg file:border-0 file:bg-raised file:px-3 file:py-2 file:font-semibold"
                />
              </div>
              <div className="mt-6 flex justify-end gap-2">
                <Button variant="ghost" onClick={() => setConfirm(null)}>
                  {tc("cancel")}
                </Button>
                <Button variant="lime" disabled={act.busy} onClick={confirmDelivery}>
                  {t("delivery.confirm")}
                </Button>
              </div>
            </>
          ) : (
            <>
              <DialogTitle>{confirm === "delete" ? t("confirmDelete.title") : t("confirmWithdraw.title")}</DialogTitle>
              <DialogDescription>{confirm === "delete" ? t("confirmDelete.body") : t("confirmWithdraw.body")}</DialogDescription>
              <div className="mt-6 flex justify-end gap-2">
                <Button variant="ghost" onClick={() => setConfirm(null)}>
                  {tc("cancel")}
                </Button>
                <Button
                  variant="danger"
                  disabled={act.busy}
                  onClick={async () => {
                    if (confirm === "delete") {
                      await act.run(() => api.deleteCase(c.id));
                      router.push("/cases");
                    } else {
                      await act.run(() => api.withdraw(c.id));
                      setConfirm(null);
                      void reload();
                    }
                  }}
                >
                  {confirm === "delete" ? t("delete") : t("withdraw")}
                </Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
      <p className="text-xs text-muted">{t("created", { when: formatDateTime(c.created_at, ui) ?? "" })}</p>
    </div>
  );
}
