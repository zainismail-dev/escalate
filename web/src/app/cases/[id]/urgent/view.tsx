"use client";
import { AlertOctagon, ArrowRight, BadgeAlert, KeyRound, Loader2, ShieldX } from "lucide-react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { AgentProgress, lastEventId } from "@/components/agent-progress";
import { ErrorState, PageSkeleton } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { api } from "@/lib/api";
import { countryName } from "@/lib/format";
import { useAction, useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";
import { CaseHeader } from "../case-header";

/** Playbook text with an unresolved TODO(verify) is shown without the TODO, marked unverified. */
function clean(detail: string): { text: string; unverified: boolean } {
  const unverified = /TODO\(verify\)/.test(detail);
  return { text: detail.replace(/TODO\(verify\):[^.]*\.\s*/g, "").trim(), unverified };
}

function useChecked(caseId: number) {
  const key = `escalate:checklist:${caseId}`;
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  useEffect(() => {
    try {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setChecked(JSON.parse(localStorage.getItem(key) || "{}"));
    } catch {
      /* private mode */
    }
  }, [key]);
  const toggle = (id: string, v: boolean) =>
    setChecked((prev) => {
      const next = { ...prev, [id]: v };
      try {
        localStorage.setItem(key, JSON.stringify(next));
      } catch {
        /* private mode */
      }
      return next;
    });
  return { checked, toggle };
}

export function UrgentChecklist({ id }: { id: number }) {
  const t = useTranslations("urgent");
  const ui = useLocale();
  const router = useRouter();
  const caseQ = useApi(() => api.getCase(id), [id]);
  const country = caseQ.data?.country;
  const listQ = useApi(() => (caseQ.data ? api.checklist(country) : Promise.resolve(null)), [caseQ.data?.id, country]);
  const { checked, toggle } = useChecked(id);
  const act = useAction();
  const [running, setRunning] = useState(false);
  const [since, setSince] = useState(0);

  const c = caseQ.data;
  const list = listQ.data;
  if ((caseQ.loading && !c) || (listQ.loading && !list)) return <PageSkeleton />;
  if (caseQ.error && !c) return <ErrorState error={caseQ.error} onRetry={caseQ.reload} />;
  if (!c || !list) return listQ.error ? <ErrorState error={listQ.error} onRetry={listQ.reload} /> : null;

  const urgent = list.items.filter((i) => i.urgent);
  const later = list.items.filter((i) => !i.urgent);
  const generic = list.country === "INTL";
  const allDone = urgent.every((i) => checked[i.id]);
  const waiting = c.waiting_for === "urgent_checklist";

  async function done() {
    setSince(await lastEventId(id));
    setRunning(true);
    const out = await act.run(() => api.ackChecklist(id));
    setRunning(false);
    if (out) router.push(out.waiting_for === "questions" ? `/cases/new?case=${id}` : `/cases/${id}`);
  }

  return (
    <div className="space-y-6">
      <div role="alert" className="rounded-2xl bg-danger p-5 text-white dark:text-night" data-testid="urgent-banner">
        <p className="flex items-center gap-2 font-display text-2xl">
          <AlertOctagon className="size-7" aria-hidden />
          {t("banner.title")}
        </p>
        <p className="mt-1 max-w-2xl text-sm opacity-95">{t("banner.body")}</p>
      </div>

      <CaseHeader c={c} back={{ href: `/cases/${c.id}`, label: t("backToCase") }} title={t("title")} />
      {act.error && <ErrorState error={act.error} />}

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <section aria-labelledby="steps" className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id="steps" className="font-display text-xl">{t("stepsTitle")}</h2>
            {generic ? (
              <Badge tone="warning">{t("generic", { country: countryName(c.country, ui) ?? t("yourCountry") })}</Badge>
            ) : (
              <Badge tone="success">{t("local", { country: countryName(list.country, ui) ?? list.country })}</Badge>
            )}
          </div>
          <ol className="space-y-3" data-testid="urgent-steps">
            {urgent.map((item, i) => {
              const d = clean(item.detail);
              const cid = `step-${item.id}`;
              return (
                <li key={item.id} className={cn("flex gap-4 rounded-2xl border bg-card p-4", checked[item.id] ? "border-success" : "border-line-strong")}>
                  <Checkbox id={cid} checked={!!checked[item.id]} onCheckedChange={(v) => toggle(item.id, v === true)} aria-describedby={`${cid}-d`} />
                  <div className="min-w-0">
                    <label htmlFor={cid} className="flex flex-wrap items-center gap-2 font-semibold">
                      <span className="label-mono text-muted">{String(i + 1).padStart(2, "0")}</span>
                      {item.title}
                      {d.unverified && <Badge tone="warning">{t("unverified")}</Badge>}
                    </label>
                    <p id={`${cid}-d`} className="mt-1 text-sm text-text-2">
                      {d.text || t("unverifiedDetail")}
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
          {later.length > 0 && (
            <div className="rounded-2xl border border-line bg-card p-4">
              <p className="label-mono text-muted">{t("also")}</p>
              <ul className="mt-2 space-y-2 text-sm">
                {later.map((i) => (
                  <li key={i.id}>
                    <span className="font-semibold">{i.title}.</span> <span className="text-text-2">{clean(i.detail).text}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {running && <AgentProgress caseId={id} running={running} since={since} />}
          {waiting ? (
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="lime" size="lg" disabled={!allDone || running} onClick={done} data-testid="urgent-done">
                {running ? <Loader2 className="animate-spin" aria-hidden /> : null}
                {t("done")}
                <ArrowRight className="rtl:rotate-180" aria-hidden />
              </Button>
              {!allDone && <p className="text-xs text-muted">{t("checkAll", { count: urgent.length })}</p>}
            </div>
          ) : (
            <p className="text-sm text-success">{t("acknowledged")}</p>
          )}
        </section>

        <aside className="space-y-4">
          <section className="rounded-2xl border-[1.5px] border-line-strong bg-card p-5" aria-labelledby="never" data-testid="never-share">
            <h2 id="never" className="flex items-center gap-2 font-display text-lg">
              <KeyRound className="size-5" aria-hidden />
              {t("never.title")}
            </h2>
            <ul className="mt-3 space-y-2 text-sm text-text-2">
              {(["password", "pin", "otp", "card"] as const).map((k) => (
                <li key={k} className="flex items-center gap-2">
                  <ShieldX className="size-4 shrink-0 text-danger" aria-hidden />
                  {t(`never.${k}`)}
                </li>
              ))}
            </ul>
            <p className="mt-3 rounded-xl bg-raised p-3 text-xs text-text-2">{t("never.us")}</p>
          </section>
          <section className="rounded-2xl border border-warning bg-warning-bg p-5" aria-labelledby="recovery" data-testid="recovery-warning">
            <h2 id="recovery" className="flex items-center gap-2 font-display text-lg text-text">
              <BadgeAlert className="size-5 text-warning" aria-hidden />
              {t("recovery.title")}
            </h2>
            <p className="mt-2 text-sm text-text-2">{t("recovery.body")}</p>
          </section>
          {list.sources.length > 0 && (
            <div className="text-xs text-muted">
              <p className="label-mono">{t("sources")}</p>
              <ul className="mt-1 space-y-1">
                {list.sources.map((s) => (
                  <li key={s.title}>
                    {s.url ? (
                      <a className="text-info underline" href={s.url} target="_blank" rel="noreferrer noopener">
                        {s.title.replace(/\s*—?\s*TODO:.*$/, "")}
                      </a>
                    ) : (
                      s.title.replace(/\s*—?\s*TODO:.*$/, "") || t("sourcePending")
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
