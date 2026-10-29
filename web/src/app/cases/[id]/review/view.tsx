"use client";
import { CheckCircle2, Columns2, Languages, Loader2, Pencil, Send, ShieldCheck, XCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { AgentProgress, lastEventId } from "@/components/agent-progress";
import { useFactLabel } from "@/components/fact-chip";
import { Letter } from "@/components/letter";
import { LanguagePicker } from "@/components/pickers";
import { RecipientConfirm } from "@/components/recipient-confirm";
import { ErrorState, FactCheckBlocked, PageSkeleton } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { FieldHint, Input, Label, Textarea } from "@/components/ui/input";
import { WhyPanel } from "@/components/why-panel";
import { dirFor, primaryLanguage } from "@/i18n/config";
import { api } from "@/lib/api";
import { languageName } from "@/lib/format";
import type { Preview, Review } from "@/lib/types";
import { useLetterLanguages } from "@/lib/letter-languages";
import { useAction, useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";
import { CaseHeader } from "../case-header";

export function ReviewDraft({ id }: { id: string }) {
  const t = useTranslations("review");
  const tc = useTranslations("common");
  const tch = useTranslations("channel");
  const ui = useLocale();
  const router = useRouter();
  const factLabel = useFactLabel();
  const caseQ = useApi(() => api.getCase(id), [id]);
  // v0.1 is English-only: the language pickers and side-by-side view stay hidden (see DECISIONS).
  const multiLanguage = useLetterLanguages().length > 1;
  const msgId = caseQ.data?.pending_draft?.id;
  const reviewQ = useApi<Review | null>(() => (msgId ? api.review(msgId) : Promise.resolve(null)), [msgId]);
  const act = useAction();
  const [editing, setEditing] = useState(false);
  const [draftBody, setDraftBody] = useState("");
  const [draftSubject, setDraftSubject] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [compare, setCompare] = useState<string | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [dialog, setDialog] = useState<"approve" | "reject" | null>(null);
  // The address the user ticked "I checked" for: any change to the recipient un-ticks it.
  const [checkedRecipient, setCheckedRecipient] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [redrafting, setRedrafting] = useState(false);
  const [since, setSince] = useState(0);

  const c = caseQ.data;
  const r = reviewQ.data;

  if ((caseQ.loading && !c) || (reviewQ.loading && !r && msgId)) return <PageSkeleton />;
  if (caseQ.error && !c) return <ErrorState error={caseQ.error} onRetry={caseQ.reload} />;
  if (!c) return null;

  if (!msgId || !r) {
    return (
      <div className="space-y-6">
        <CaseHeader c={c} heading={t("noDraft.title")} />
        <div className="rounded-2xl border border-dashed border-line bg-card p-10 text-center" data-testid="no-draft">
          <h2 className="font-display text-xl">{t("noDraft.title")}</h2>
          <p className="mt-1 text-sm text-text-2">{t("noDraft.body")}</p>
          <Button className="mt-4" asChild>
            <Link href={`/cases/${c.id}`}>{t("backToCase")}</Link>
          </Button>
        </div>
      </div>
    );
  }

  const msg = r.message;
  const blocked = r.problems.length > 0;
  const blanksLeft = r.blanks.length;
  const reloadAll = async () => {
    await caseQ.reload();
    await reviewQ.reload();
  };

  async function saveEdit() {
    const out = await act.run(() => api.editMessage(msg.id, draftBody, draftSubject || null));
    if (out) {
      setWarnings(out.warnings);
      setEditing(false);
      await reviewQ.reload();
    }
  }

  async function showCompare(lang: string) {
    setCompare(lang);
    setPreview(null);
    const p = await act.run(() => api.preview(msg.id, lang));
    if (p) setPreview(p);
  }

  async function switchLanguage(lang: string) {
    setSince(await lastEventId(c!.id));
    setRedrafting(true);
    await act.run(() => api.setLetterLanguage(c!.id, lang));
    setRedrafting(false);
    setCompare(null);
    setPreview(null);
    await reloadAll();
  }

  async function approve() {
    const out = await act.run(() => api.approve(msg.id, msg.recipient));
    if (out) {
      router.push(`/cases/${c!.id}`);
      return;
    }
    setDialog(null);
    await reviewQ.reload(); // shows what blocked it
  }

  async function reject() {
    setDialog(null);
    setSince(await lastEventId(c!.id));
    setRedrafting(true);
    await act.run(() => api.reject(msg.id, rejectReason));
    setRedrafting(false);
    setRejectReason("");
    await reloadAll();
  }

  const failingChecks = r.checks.filter((ch) => !ch.ok);
  const recipientOk = !msg.recipient || checkedRecipient === msg.recipient;
  const approveDisabledReason = blanksLeft
    ? t("decision.fillBlanks", { count: blanksLeft })
    : !r.checks.find((ch) => ch.id === "facts")?.ok
      ? t("decision.fixFacts")
      : !recipientOk
        ? t("decision.checkRecipient")
        : null;

  return (
    <div className="space-y-6">
      <CaseHeader c={c} heading={t("title", { step: r.step_name ?? "" })} />

      {act.error && act.error.kind !== "fact_check" && <ErrorState error={act.error} />}
      {act.error?.kind === "fact_check" ? (
        <FactCheckBlocked problems={r.problems} facts={r.facts} other={act.error.issues.filter((i) => !/is not in the case facts/.test(i))} />
      ) : (
        blocked && <FactCheckBlocked problems={r.problems} facts={r.facts} />
      )}
      {redrafting && <AgentProgress caseId={c.id} running since={since} />}

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        {/* Letter */}
        <div className="min-w-0 space-y-4">
          {multiLanguage && (
          <div className="flex flex-wrap items-end gap-3 rounded-2xl border border-line bg-card p-3">
            <div className="min-w-44 flex-1">
              <LanguagePicker
                id="letter-lang"
                value={r.language}
                available={r.template_languages}
                label={t("letterLanguage")}
                onChange={(lang) => lang !== r.language && switchLanguage(lang)}
              />
            </div>
            <div className="min-w-44 flex-1">
              <LanguagePicker
                id="compare-lang"
                value={compare ?? r.template_languages.find((l) => l !== primaryLanguage(r.language)) ?? "en"}
                available={r.template_languages}
                label={t("compareWith")}
                onChange={showCompare}
              />
            </div>
            <Button
              variant={compare ? "ink" : "outline"}
              aria-pressed={!!compare}
              onClick={() =>
                compare ? (setCompare(null), setPreview(null)) : showCompare(r.template_languages.find((l) => l !== primaryLanguage(r.language)) ?? "en")
              }
            >
              <Columns2 aria-hidden />
              {t("sideBySide")}
            </Button>
            <Button
              variant={editing ? "ink" : "outline"}
              aria-pressed={editing}
              onClick={() => {
                setDraftBody(msg.body);
                setDraftSubject(msg.subject ?? "");
                setEditing(!editing);
              }}
            >
              <Pencil aria-hidden />
              {t("edit")}
            </Button>
          </div>
          )}

          <div className="flex flex-wrap gap-3 text-xs text-text-2">
            <span className="inline-flex items-center gap-1.5">
              <span className="fact-mark">Aa</span> {t("legend.fact")}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="blank-mark">[[ ]]</span> {t("legend.blank")}
            </span>
            <span className="label-mono ms-auto text-muted">
              {tch(msg.channel)} · {msg.recipient ?? t("noRecipient")}
            </span>
          </div>

          {editing ? (
            <div className="space-y-3 rounded-2xl border border-line bg-card p-4">
              <div className="space-y-1.5">
                <Label htmlFor="subject">{t("subject")}</Label>
                <Input id="subject" value={draftSubject} onChange={(e) => setDraftSubject(e.target.value)} dir={r.text_direction} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="body">{t("body")}</Label>
                <Textarea
                  id="body"
                  value={draftBody}
                  onChange={(e) => setDraftBody(e.target.value)}
                  dir={r.text_direction}
                  lang={r.language}
                  className="letter min-h-96 font-serif"
                />
                <FieldHint>{t("editHint")}</FieldHint>
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="ghost" onClick={() => setEditing(false)}>
                  {tc("cancel")}
                </Button>
                <Button variant="ink" disabled={act.busy} onClick={saveEdit}>
                  {tc("save")}
                </Button>
              </div>
            </div>
          ) : (
            <div className={cn("grid gap-4", compare && "xl:grid-cols-2")}>
              <div>
                {compare && <p className="label-mono mb-2 text-muted">{t("thisDraft", { language: languageName(r.language, ui) ?? r.language })}</p>}
                <Letter
                  subject={r.subject_segments}
                  body={r.body_segments}
                  lang={r.language}
                  dir={r.text_direction}
                  factLabel={(k) => t("verifiedFact", { fact: factLabel(k) })}
                  blankLabel={t("legend.blank")}
                  testId="letter"
                />
              </div>
              {compare && (
                <div>
                  <p className="label-mono mb-2 text-muted">{t("previewOf", { language: languageName(compare, ui) ?? compare })}</p>
                  {!preview ? (
                    <div className="grid h-40 place-items-center rounded-md border border-line bg-card">
                      <Loader2 className="size-5 animate-spin text-muted" aria-label={tc("loading")} />
                    </div>
                  ) : preview.available ? (
                    <>
                      <Letter
                        subject={preview.subject}
                        body={preview.body ?? ""}
                        lang={preview.language}
                        dir={preview.text_direction}
                        factLabel={() => ""}
                        blankLabel=""
                        testId="letter-preview"
                      />
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <p className="flex-1 text-xs text-muted">{t("previewNote")}</p>
                        <Button size="sm" variant="ink" disabled={redrafting} onClick={() => switchLanguage(preview.language)}>
                          <Languages aria-hidden />
                          {t("useLanguage", { language: languageName(preview.language, ui) ?? preview.language })}
                        </Button>
                      </div>
                    </>
                  ) : (
                    <div className="rounded-md border border-dashed border-line bg-card p-6 text-sm" dir={dirFor(compare)}>
                      <p className="text-text-2">{t("noTemplate", { language: languageName(compare, ui) ?? compare })}</p>
                      <Button size="sm" className="mt-3" disabled={redrafting} onClick={() => switchLanguage(compare)}>
                        <Languages aria-hidden />
                        {t("askRedraft")}
                      </Button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
          {warnings.length > 0 && (
            <ul className="rounded-xl bg-warning-bg p-3 text-xs text-warning">
              {warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
        </div>

        {/* Decision + facts + checks */}
        <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <section className="rounded-2xl border-[1.5px] border-line-strong bg-card p-5" aria-labelledby="decision" data-testid="decision-card">
            <p className="label-mono text-muted">{t("decision.eyebrow")}</p>
            <h2 id="decision" className="mt-1 font-display text-xl">{t("decision.title")}</h2>
            <p className="mt-1 text-sm text-text-2">{t("decision.body", { recipient: msg.recipient ?? t("noRecipient"), channel: tch(msg.channel) })}</p>
            {r.recipient_check && (
              <RecipientConfirm
                key={`${msg.id}:${msg.recipient}`}
                check={r.recipient_check}
                messageId={msg.id}
                checked={checkedRecipient === msg.recipient}
                onChecked={(v) => setCheckedRecipient(v ? msg.recipient : null)}
                onChanged={() => void reviewQ.reload()}
              />
            )}
            <Button
              variant="lime"
              size="lg"
              className="mt-4 w-full"
              disabled={!r.can_approve || !recipientOk || act.busy || redrafting}
              aria-describedby={approveDisabledReason ? "approve-why" : undefined}
              onClick={() => setDialog("approve")}
              data-testid="approve"
            >
              <Send aria-hidden />
              {t("decision.approve")}
            </Button>
            {approveDisabledReason && (
              <p id="approve-why" className="mt-2 text-xs font-semibold text-warning" data-testid="approve-why">
                {approveDisabledReason}
              </p>
            )}
            <div className="mt-3 grid grid-cols-2 gap-2">
              <Button
                onClick={() => {
                  setDraftBody(msg.body);
                  setDraftSubject(msg.subject ?? "");
                  setEditing(true);
                }}
              >
                <Pencil aria-hidden />
                {t("edit")}
              </Button>
              <Button onClick={() => setDialog("reject")} disabled={redrafting}>
                <XCircle aria-hidden />
                {t("decision.reject")}
              </Button>
            </div>
            <p className="mt-3 flex items-center gap-1.5 text-xs text-muted">
              <ShieldCheck className="size-3.5" aria-hidden />
              {t("decision.youApprove")}
            </p>
          </section>

          <Card>
            <CardHeader>
              <CardTitle>{t("checks.title")}</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2" data-testid="checks">
                {r.checks.map((ch) => (
                  <li key={ch.id} className="flex gap-2 text-sm">
                    {ch.ok ? (
                      <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
                    ) : (
                      <XCircle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />
                    )}
                    <span>
                      <span className="sr-only">{ch.ok ? t("checks.pass") : t("checks.fail")}: </span>
                      {t(`checks.${ch.id}`)}
                      {!ch.ok && ch.detail.length > 0 && <span className="block font-mono text-xs text-danger">{ch.detail.join(" · ")}</span>}
                    </span>
                  </li>
                ))}
              </ul>
              {failingChecks.length === 0 && <p className="mt-3 text-xs text-success">{t("checks.allGood")}</p>}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t("factsTitle")}</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {r.facts.map((f) => (
                  <li key={f.key} className="text-sm">
                    <p className="label-mono text-muted">
                      {factLabel(f.key)}
                      {f.used && <span className="ms-1 text-success">· {t("used")}</span>}
                    </p>
                    <p className={cn("w-fit break-all font-semibold", f.used && "fact-mark")}>{f.display.at(-1) ?? f.value}</p>
                    <p className="text-[0.6875rem] text-muted">{f.source_filename ? t("fromFile", { file: f.source_filename }) : t("fromYou")}</p>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          {c.reasons.length > 0 && <WhyPanel reasons={c.reasons} playbook={c.playbook_id} version={c.playbook_version} />}
        </aside>
      </div>

      <Dialog open={dialog !== null} onOpenChange={(o) => !o && setDialog(null)}>
        <DialogContent closeLabel={tc("close")}>
          {dialog === "approve" ? (
            <>
              <DialogTitle>{t("confirm.title")}</DialogTitle>
              <DialogDescription>
                {t("confirm.body", { recipient: msg.recipient ?? t("noRecipient"), channel: tch(msg.channel) })}
              </DialogDescription>
              <ul className="mt-4 space-y-1 text-sm text-text-2">
                {msg.recipient && <li>✓ {t("confirm.recipient", { recipient: msg.recipient })}</li>}
                <li>✓ {t("confirm.facts")}</li>
                <li>✓ {t("confirm.noBlanks")}</li>
                <li>✓ {t("confirm.disclaimer")}</li>
              </ul>
              <div className="mt-6 flex justify-end gap-2">
                <Button variant="ghost" onClick={() => setDialog(null)}>
                  {tc("cancel")}
                </Button>
                <Button variant="lime" disabled={act.busy} onClick={approve} data-testid="confirm-approve">
                  {act.busy ? <Loader2 className="animate-spin" aria-hidden /> : <Send aria-hidden />}
                  {t("confirm.cta")}
                </Button>
              </div>
            </>
          ) : (
            <>
              <DialogTitle>{t("rejectDialog.title")}</DialogTitle>
              <DialogDescription>{t("rejectDialog.body")}</DialogDescription>
              <div className="mt-4 space-y-1.5">
                <Label htmlFor="reject-reason">{t("rejectDialog.reason")}</Label>
                <Textarea id="reject-reason" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
              </div>
              <div className="mt-6 flex justify-end gap-2">
                <Button variant="ghost" onClick={() => setDialog(null)}>
                  {tc("cancel")}
                </Button>
                <Button variant="ink" onClick={reject}>
                  {t("rejectDialog.cta")}
                </Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
