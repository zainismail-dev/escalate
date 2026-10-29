"use client";
import { Check, Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Agent stages and the timeline event that marks each one done. */
export type Stages = [string, string[]][];

export const DRAFT_STAGES: Stages = [
  ["classify", ["classified"]],
  ["playbook", ["playbook_selected"]],
  ["facts", ["facts_extracted", "extraction_failed", "answers_saved"]],
  ["draft", ["draft_created"]],
  ["check", ["fact_checked"]],
];

export const REPLY_STAGES: Stages = [
  ["reply", ["reply_logged"]],
  ["judge", ["reply_judged"]],
  ["next", ["next_step", "case_resolved", "ladder_complete", "verdict_overridden"]],
  ["draft", ["draft_created"]],
  ["check", ["fact_checked"]],
];

/** While `running`, polls the case timeline and ticks off what the agent has really done. */
export function AgentProgress({
  caseId,
  running,
  since,
  stages = DRAFT_STAGES,
}: {
  caseId: string;
  running: boolean;
  since: number;
  stages?: Stages;
}) {
  const t = useTranslations("progress");
  const [seen, setSeen] = useState<Set<string>>(new Set());
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback(async () => {
    try {
      const events = await api.timeline(caseId);
      setSeen(new Set(events.filter((e) => e.id > since).map((e) => e.type)));
    } catch {
      /* the main request reports errors */
    }
  }, [caseId, since]);

  useEffect(() => {
    if (!running) return;
    const first = setTimeout(poll, 0);
    timer.current = setInterval(poll, 900);
    return () => {
      clearTimeout(first);
      if (timer.current) clearInterval(timer.current);
    };
  }, [running, poll]);

  const done = stages.map(([, evs]) => evs.some((e) => seen.has(e)));
  const currentIdx = done.lastIndexOf(true) + 1;
  return (
    <div className="rounded-2xl border-[1.5px] border-line-strong bg-card p-5" aria-live="polite" data-testid="agent-progress">
      <div className="flex items-center gap-2">
        <span className="label-mono rounded-md bg-lime px-1.5 py-0.5 font-bold text-on-lime">{t("agent")}</span>
        <h2 className="font-display text-lg">{running ? t("working") : t("finished")}</h2>
      </div>
      <ol className="mt-4 space-y-2.5">
        {stages.map(([id], i) => {
          const isDone = done[i] || (!running && i < currentIdx);
          const isCurrent = running && i === currentIdx;
          return (
            <li key={id} className={cn("flex items-center gap-3 text-sm", !isDone && !isCurrent && "text-muted")}>
              <span
                className={cn(
                  "grid size-6 place-items-center rounded-full border",
                  isDone && "border-ink bg-ink text-bg",
                  isCurrent && "border-ink bg-lime text-on-lime",
                  !isDone && !isCurrent && "border-dashed border-muted",
                )}
              >
                {isDone ? <Check className="size-3.5" aria-hidden /> : isCurrent ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
              </span>
              <span className={cn(isCurrent && "font-semibold text-text")}>{t(`steps.${id}`)}</span>
              <span className="sr-only">{isDone ? t("done") : isCurrent ? t("inProgress") : t("pending")}</span>
            </li>
          );
        })}
      </ol>
      <p className="mt-4 text-xs text-muted">{t("note")}</p>
    </div>
  );
}

/** Highest event id so far, so progress only counts what happens after a click. */
export async function lastEventId(caseId: string): Promise<number> {
  try {
    const ev = await api.timeline(caseId);
    return ev.reduce((m, e) => Math.max(m, e.id), 0);
  } catch {
    return 0;
  }
}
