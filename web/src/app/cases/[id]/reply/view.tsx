"use client";
import { ArrowRight, Gavel, Loader2 } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { AgentProgress, lastEventId, REPLY_STAGES } from "@/components/agent-progress";
import { ResolutionConfirm } from "@/components/resolution-confirm";
import { ErrorState, PageSkeleton } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { FieldHint, Label, NativeSelect, Textarea } from "@/components/ui/input";
import { api } from "@/lib/api";
import { caseLocale, formatDate, formatDateTime } from "@/lib/format";
import type { ReplyOut } from "@/lib/types";
import { useAction, useApi } from "@/lib/use-api";
import { CaseHeader } from "../case-header";

const VERDICTS = ["resolved", "partial", "refused", "no_reply"] as const;
const TONE = { resolved: "success", partial: "warning", refused: "danger", no_reply: "neutral" } as const;

export function LogReply({ id }: { id: number }) {
  const t = useTranslations("reply");
  const tv = useTranslations("verdict");
  const caseQ = useApi(() => api.getCase(id), [id]);
  const act = useAction();
  const [text, setText] = useState("");
  const [result, setResult] = useState<ReplyOut | null>(null);
  const [running, setRunning] = useState(false);
  const [since, setSince] = useState(0);
  const [override, setOverride] = useState<string>("");

  const c = caseQ.data;
  if (caseQ.loading && !c) return <PageSkeleton />;
  if (caseQ.error && !c) return <ErrorState error={caseQ.error} onRetry={caseQ.reload} />;
  if (!c) return null;
  const locale = caseLocale(c.language, c.country);

  async function submit() {
    setSince(await lastEventId(id));
    setRunning(true);
    const out = await act.run(() => api.logReply(id, text));
    setRunning(false);
    if (out) {
      setResult(out);
      setOverride(out.verdict ?? "");
    }
    await caseQ.reload();
  }

  async function correct() {
    if (!override || override === result?.verdict) return;
    setSince(await lastEventId(id));
    setRunning(true);
    const out = await act.run(() => api.overrideVerdict(id, override));
    setRunning(false);
    if (out && result) setResult({ ...result, verdict: override as ReplyOut["verdict"], reason: t("overridden") });
    await caseQ.reload();
  }

  const waiting = c.waiting_for === "waiting_reply";
  const confirming = c.waiting_for === "confirm_resolution";
  return (
    <div className="space-y-6">
      <CaseHeader c={c} heading={t("title")} />
      {act.error && <ErrorState error={act.error} />}

      {confirming && <ResolutionConfirm caseId={c.id} reason={result?.reason} onDone={() => void caseQ.reload()} />}

      {!result && !waiting && !confirming && (
        <div className="rounded-2xl border border-dashed border-line bg-card p-8 text-center" data-testid="not-waiting">
          <p className="text-text-2">{t("notWaiting")}</p>
          <Button className="mt-3" asChild>
            <Link href={`/cases/${c.id}`}>{t("backToCase")}</Link>
          </Button>
        </div>
      )}

      {!result && waiting && (
        <Card>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="reply-text">{t("paste")}</Label>
              <Textarea
                id="reply-text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                className="min-h-52"
                placeholder={t("placeholder")}
                aria-describedby="reply-hint"
              />
              <FieldHint id="reply-hint">
                {c.next_action_at ? t("autoMove", { when: formatDateTime(c.next_action_at, locale) ?? "" }) : t("hint")}
              </FieldHint>
            </div>
            <div className="flex justify-end">
              <Button variant="lime" size="lg" disabled={!text.trim() || running} onClick={submit}>
                {running ? <Loader2 className="animate-spin" aria-hidden /> : <Gavel aria-hidden />}
                {t("judge")}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {running && <AgentProgress caseId={id} running={running} since={since} stages={REPLY_STAGES} />}

      {result && result.verdict && !confirming && (
        <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
          <section className="rounded-2xl border-[1.5px] border-line-strong bg-card p-5" aria-labelledby="verdict" data-testid="verdict-card">
            <div className="flex items-center gap-2">
              <span className="label-mono rounded-md bg-lime px-1.5 py-0.5 font-bold text-on-lime">{t("agent")}</span>
              <h2 id="verdict" className="font-display text-lg">{t("verdictTitle")}</h2>
            </div>
            <Badge tone={TONE[result.verdict]} className="mt-4 px-3 py-1 text-sm">
              {tv(result.verdict)}
            </Badge>
            <dl className="mt-5 grid gap-4 sm:grid-cols-3">
              <div>
                <dt className="label-mono text-muted">{t("offered")}</dt>
                <dd className="mt-1 text-sm font-semibold">{result.promise ?? t("nothing")}</dd>
              </div>
              <div>
                <dt className="label-mono text-muted">{t("byWhen")}</dt>
                <dd className="mt-1 text-sm font-semibold">{result.promise_date ? formatDate(result.promise_date, locale, "long") : t("noDate")}</dd>
              </div>
              <div>
                <dt className="label-mono text-muted">{t("condition")}</dt>
                <dd className="mt-1 text-sm font-semibold">{result.condition ?? t("none")}</dd>
              </div>
            </dl>
            <div className="mt-5 border-t border-line pt-4">
              <p className="label-mono text-muted">{t("reasoning")}</p>
              <p className="mt-1 text-sm text-text-2">{result.reason || "—"}</p>
            </div>
            <div className="mt-5 border-t border-line pt-4">
              <Label htmlFor="override">{t("override")}</Label>
              <div className="mt-1.5 flex flex-wrap gap-2">
                <NativeSelect id="override" value={override} onChange={(e) => setOverride(e.target.value)} className="w-auto flex-1">
                  {VERDICTS.map((v) => (
                    <option key={v} value={v}>
                      {tv(v)}
                    </option>
                  ))}
                </NativeSelect>
                <Button disabled={running || override === result.verdict} onClick={correct}>
                  {t("overrideCta")}
                </Button>
              </div>
              <FieldHint className="mt-1">{t("overrideHint")}</FieldHint>
            </div>
          </section>
          <section className="rounded-2xl border border-line bg-card p-5" aria-labelledby="next" data-testid="reply-next">
            <p className="label-mono text-muted">{t("nextStep")}</p>
            <h2 id="next" className="mt-1 font-display text-xl">
              {c.status === "resolved" ? t("resolvedTitle") : (c.step_name ?? t("ladderDone"))}
            </h2>
            <p className="mt-1 text-sm text-text-2">{c.status === "resolved" ? t("resolvedBody") : t("nextBody")}</p>
            <Button variant="lime" size="lg" className="mt-4" asChild>
              <Link href={c.waiting_for === "approve_draft" ? `/cases/${c.id}/review` : c.waiting_for === "questions" ? `/cases/${c.id}/questions` : `/cases/${c.id}`}>
                {c.waiting_for === "approve_draft" ? t("reviewNext") : c.waiting_for === "questions" ? t("answerNext") : t("backToCase")}
                <ArrowRight className="rtl:rotate-180" aria-hidden />
              </Link>
            </Button>
          </section>
        </div>
      )}
    </div>
  );
}
