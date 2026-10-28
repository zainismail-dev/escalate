import { Check } from "lucide-react";
import { useTranslations } from "next-intl";
import type { LadderStep } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * The Escalation Ladder: rungs rise left to right (start to end in RTL). Done rungs are ink,
 * the current rung is lime, future rungs are dashed, skipped rungs are faded.
 */
export function EscalationLadder({ steps, className }: { steps: LadderStep[]; className?: string }) {
  const t = useTranslations("ladder");
  const tc = useTranslations("channel");
  const n = steps.length;
  return (
    <ol className={cn("grid items-end gap-2 sm:gap-3", className)} style={{ gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))` }}>
      {steps.map((s, i) => {
        const height = 40 + Math.round((i / Math.max(n - 1, 1)) * 64);
        return (
          <li key={s.id} aria-current={s.state === "current" ? "step" : undefined} className="flex min-w-0 flex-col gap-2">
            <div
              className={cn(
                "relative flex items-start justify-between rounded-xl p-2",
                s.state === "done" && "bg-ink text-bg",
                s.state === "current" && "bg-lime text-on-lime ring-2 ring-ink dark:ring-lime",
                s.state === "future" && "border-2 border-dashed border-muted/70 text-muted",
                s.state === "skipped" && "border border-dotted border-line text-muted opacity-60",
              )}
              style={{ height }}
            >
              <span className="label-mono font-bold">{String(i + 1).padStart(2, "0")}</span>
              {s.state === "done" && <Check className="size-4" aria-hidden />}
            </div>
            <div className="min-w-0">
              <p className={cn("text-xs font-semibold leading-tight text-text", s.state === "skipped" && "line-through text-muted")}>
                {s.name}
              </p>
              <p className="label-mono mt-0.5 truncate text-muted">
                <span className="sr-only">{t(s.state)} · </span>
                {tc(s.channel)}
                {s.wait_days ? ` · ${t("days", { days: s.wait_days })}` : ""}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** Mini ladder for case cards. */
export function MiniLadder({ steps, label }: { steps: LadderStep[]; label: string }) {
  const n = steps.length;
  return (
    <div role="img" aria-label={label} className="flex h-7 items-end gap-1">
      {steps.map((s, i) => (
        <span
          key={s.id}
          className={cn(
            "w-3 rounded-[3px]",
            s.state === "done" && "bg-ink",
            s.state === "current" && "bg-lime ring-1 ring-ink dark:ring-lime",
            s.state === "future" && "border border-dashed border-muted",
            s.state === "skipped" && "border border-dotted border-line opacity-50",
          )}
          style={{ height: 8 + Math.round((i / Math.max(n - 1, 1)) * 20) }}
        />
      ))}
    </div>
  );
}
