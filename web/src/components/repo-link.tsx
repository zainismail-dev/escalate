"use client";
import { CodeXml } from "lucide-react";
import { useTranslations } from "next-intl";
import { REPO_URL } from "@/lib/demo-mode";
import { cn } from "@/lib/utils";

/** "View code on GitHub": header, footers and the demo banner. */
export function RepoLink({ className, compact = false }: { className?: string; compact?: boolean }) {
  const t = useTranslations("demo");
  return (
    <a
      href={REPO_URL}
      target="_blank"
      rel="noreferrer noopener"
      className={cn("inline-flex items-center gap-1.5 font-semibold underline-offset-2 hover:underline", className)}
      data-testid="repo-link"
      aria-label={compact ? t("viewCode") : undefined}
    >
      <CodeXml className="size-4 shrink-0" aria-hidden />
      <span className={cn(compact && "sr-only sm:not-sr-only")}>{t("viewCode")}</span>
    </a>
  );
}
