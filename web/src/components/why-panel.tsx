import { ExternalLink } from "lucide-react";
import { useTranslations } from "next-intl";
import type { Reason } from "@/lib/types";
import { cn } from "@/lib/utils";

type T = ReturnType<typeof useTranslations>;

function reasonText(r: Reason, t: T, tv: T, tc: T, tl: T): string {
  const p = r.params;
  switch (r.code) {
    case "after_verdict":
      return t("after_verdict", { verdict: tv(String(p.verdict ?? "refused")), step: String(p.step ?? "") });
    case "channel":
      return p.recipient
        ? t("channel", { channel: tc(String(p.channel)), recipient: String(p.recipient) })
        : t("channel_only", { channel: tc(String(p.channel)) });
    case "playbook":
      return t("playbook", { level: tl(String(p.level ?? "generic")) });
    case "position":
    case "wait":
    case "skipped":
    case "proof":
    case "deadline":
    case "deadline_late":
    case "first_step":
      return t(r.code, Object.fromEntries(Object.entries(p).map(([k, v]) => [k, v ?? ""])) as Record<string, string | number>);
    default:
      return r.code;
  }
}

/** "Why this step?": the agent's reasoning, numbered, with the playbook it followed. */
export function WhyPanel({
  reasons,
  playbook,
  version,
  sources = [],
  className,
}: {
  reasons: Reason[];
  playbook: string | null;
  version?: string | null;
  sources?: { title: string; url: string | null }[];
  className?: string;
}) {
  const t = useTranslations("why");
  const tr = useTranslations("why.reasons");
  const tv = useTranslations("verdict");
  const tc = useTranslations("channel");
  const tl = useTranslations("why.level");
  const list = reasons.filter((r) => r.code !== "playbook");
  const pb = reasons.find((r) => r.code === "playbook");
  return (
    <section aria-labelledby="why-title" className={cn("rounded-2xl border-[1.5px] border-line-strong bg-card p-5", className)}>
      <div className="flex items-center gap-2">
        <span className="label-mono rounded-md bg-lime px-1.5 py-0.5 font-bold text-on-lime">{t("agent")}</span>
        <h2 id="why-title" className="font-display text-lg">{t("title")}</h2>
      </div>
      <ol className="mt-4 space-y-3">
        {list.map((r, i) => (
          <li key={`${r.code}-${i}`} className="flex gap-3 text-sm text-text-2">
            <span className="label-mono grid size-6 shrink-0 place-items-center rounded-full border border-line-strong font-bold text-text">
              {i + 1}
            </span>
            <span className="pt-0.5">{reasonText(r, tr, tv, tc, tl)}</span>
          </li>
        ))}
      </ol>
      {(playbook || pb) && (
        <div className="mt-4 border-t border-line pt-3">
          <p className="label-mono text-muted">{t("playbook")}</p>
          <p className="mt-1 font-mono text-xs text-text">
            {playbook}
            {version ? ` · v${version}` : ""}
            {pb ? ` · ${reasonText(pb, tr, tv, tc, tl)}` : ""}
          </p>
          {sources.length > 0 && (
            <ul className="mt-2 space-y-1">
              {sources.map((s) => (
                <li key={s.title} className="text-xs">
                  {s.url ? (
                    <a href={s.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-info underline-offset-2 hover:underline">
                      {s.title}
                      <ExternalLink className="size-3" aria-hidden />
                      <span className="sr-only">{t("opensNewTab")}</span>
                    </a>
                  ) : (
                    <span className="text-muted">{s.title}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
