"use client";
import { AlertTriangle, CloudOff, FolderOpen, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type ApiError, API_URL } from "@/lib/api";
import type { Problem, ReviewFact } from "@/lib/types";
import { cn } from "@/lib/utils";

export function DemoButton({ onDone, variant = "lime" }: { onDone?: (ids: string[]) => void; variant?: "lime" | "outline" }) {
  const t = useTranslations("common");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  return (
    <span className="inline-flex flex-col items-center gap-1">
      <Button
        variant={variant}
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setFailed(false);
          try {
            const r = await api.seedDemo();
            onDone?.(r.case_ids);
          } catch {
            setFailed(true);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Sparkles aria-hidden />
        {busy ? t("loadingDemo") : t("tryDemo")}
      </Button>
      {failed && <span role="alert" className="text-xs text-danger">{t("demoFailed")}</span>}
    </span>
  );
}

export function EmptyState({
  title,
  body,
  action,
  demo = true,
  onDemo,
}: {
  title: string;
  body: string;
  action?: React.ReactNode;
  demo?: boolean;
  onDemo?: (ids: string[]) => void;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-line bg-card px-6 py-12 text-center" data-testid="empty-state">
      <FolderOpen className="size-10 text-muted" aria-hidden />
      <h2 className="font-display text-xl">{title}</h2>
      <p className="max-w-md text-sm text-text-2">{body}</p>
      <div className="mt-2 flex flex-wrap items-start justify-center gap-2">
        {action}
        {demo && <DemoButton onDone={onDemo} variant={action ? "outline" : "lime"} />}
      </div>
    </div>
  );
}

/** Errors: the API is down, the AI model is offline (nothing was sent), or anything else. */
export function ErrorState({ error, onRetry, className }: { error: ApiError; onRetry?: () => void; className?: string }) {
  const t = useTranslations("errors");
  const kind = error.kind;
  if (kind === "demo") return null; // the demo dialog already says why
  const Icon = kind === "model_offline" || kind === "offline_api" ? CloudOff : AlertTriangle;
  const title = t(`${kind}.title`);
  return (
    <div role="alert" className={cn("rounded-2xl border border-danger/40 bg-danger-bg p-5", className)} data-testid={`error-${kind}`}>
      <div className="flex items-start gap-3">
        <Icon className="mt-0.5 size-5 shrink-0 text-danger" aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="font-display text-lg text-text">{title}</h2>
          <p className="mt-1 text-sm text-text-2">
            {t(`${kind}.body`, { url: API_URL })}
          </p>
          {(kind === "model_offline" || kind === "offline_api") && (
            <p className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-card px-2.5 py-1 text-xs font-semibold text-success">
              <ShieldCheck className="size-3.5" aria-hidden />
              {t("nothingSent")}
            </p>
          )}
          {kind === "other" && <p className="mt-2 break-words font-mono text-xs text-muted">{error.detail}</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            {onRetry && (
              <Button size="sm" variant="ink" onClick={onRetry}>
                <RefreshCw aria-hidden />
                {t("retry")}
              </Button>
            )}
            {kind === "model_offline" && (
              <Button size="sm" asChild>
                <Link href="/settings">{t("checkSettings")}</Link>
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/** "Draft blocked by fact check": each wrong value next to the evidence value it should match. */
export function FactCheckBlocked({ problems, facts, other = [] }: { problems: Problem[]; facts: ReviewFact[]; other?: string[] }) {
  const t = useTranslations("blocked");
  const tf = useTranslations("facts");
  const byKey = new Map(facts.map((f) => [f.key, f]));
  return (
    <div role="alert" className="rounded-2xl border-[1.5px] border-danger bg-danger-bg p-5" data-testid="fact-check-blocked">
      <h2 className="flex items-center gap-2 font-display text-lg text-text">
        <AlertTriangle className="size-5 text-danger" aria-hidden />
        {t("title")}
      </h2>
      <p className="mt-1 text-sm text-text-2">{t("body")}</p>
      <ul className="mt-3 space-y-2">
        {problems.map((p) => (
          <li key={`${p.kind}-${p.wrong}`} className="grid gap-2 rounded-xl bg-card p-3 text-sm sm:grid-cols-2">
            <div>
              <p className="label-mono text-danger">{t("inDraft")}</p>
              <p className="mt-0.5 font-mono font-semibold text-danger line-through decoration-2">{p.wrong}</p>
            </div>
            <div>
              <p className="label-mono text-success">{t("inEvidence")}</p>
              {p.expected.length === 0 ? (
                <p className="mt-0.5 text-text-2">{t("noMatch")}</p>
              ) : (
                p.expected.slice(0, 3).map((k) => {
                  const f = byKey.get(k);
                  return (
                    <p key={k} className="mt-0.5">
                      <span className="fact-mark font-mono font-semibold">{f?.display.at(-1) ?? f?.value}</span>{" "}
                      <span className="text-xs text-muted">
                        {tf.has(`${k}.label`) ? tf(`${k}.label`) : k}
                        {f?.source_filename ? ` · ${t("from", { file: f.source_filename })}` : ""}
                      </span>
                    </p>
                  );
                })
              )}
            </div>
          </li>
        ))}
        {other.map((o) => (
          <li key={o} className="rounded-xl bg-card p-3 font-mono text-xs text-text-2">{o}</li>
        ))}
      </ul>
    </div>
  );
}

export function PageSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true" aria-live="polite" data-testid="skeleton">
      <Skeleton className="h-9 w-2/3" />
      <Skeleton className="h-5 w-1/3" />
      <div className="grid gap-4 md:grid-cols-3">
        <Skeleton className="h-40 md:col-span-2" />
        <Skeleton className="h-40" />
      </div>
      <Skeleton className="h-64" />
    </div>
  );
}
