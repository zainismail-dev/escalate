"use client";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { AgentProgress, lastEventId } from "@/components/agent-progress";
import { QuestionsForm } from "@/components/questions-form";
import { ErrorState, PageSkeleton } from "@/components/states";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/use-api";
import Link from "next/link";
import { CaseHeader } from "../case-header";

export function CaseQuestions({ id }: { id: number }) {
  const t = useTranslations("questions");
  const router = useRouter();
  const caseQ = useApi(() => api.getCase(id), [id]);
  const act = useAction();
  const [running, setRunning] = useState(false);
  const [since, setSince] = useState(0);
  const c = caseQ.data;
  if (caseQ.loading && !c) return <PageSkeleton />;
  if (caseQ.error && !c) return <ErrorState error={caseQ.error} onRetry={caseQ.reload} />;
  if (!c) return null;

  async function submit(answers: Record<string, string>) {
    setSince(await lastEventId(id));
    setRunning(true);
    const out = await act.run(() => api.answers(id, answers));
    setRunning(false);
    if (out?.waiting_for === "approve_draft") router.push(`/cases/${id}/review`);
    else await caseQ.reload();
  }

  return (
    <div className="space-y-6">
      <CaseHeader c={c} back={{ href: `/cases/${c.id}`, label: t("backToCase") }} title={t("title")} />
      {act.error && <ErrorState error={act.error} />}
      {c.waiting_for === "questions" ? (
        <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
          <QuestionsForm missing={c.pending?.missing ?? []} busy={running} onSubmit={submit} />
          {running && <AgentProgress caseId={id} running since={since} />}
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-line bg-card p-8 text-center">
          <p className="text-text-2">{t("nothing")}</p>
          <Button className="mt-3" asChild>
            <Link href={`/cases/${c.id}`}>{t("backToCase")}</Link>
          </Button>
        </div>
      )}
    </div>
  );
}
