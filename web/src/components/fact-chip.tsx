import { FileText, UserRound } from "lucide-react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";

export function FactChip({
  label,
  value,
  source,
  className,
}: {
  label: string;
  value: string;
  source?: string | null;
  className?: string;
}) {
  const t = useTranslations("facts");
  return (
    <li className={cn("flex min-w-0 flex-col rounded-xl border border-line bg-card px-3 py-2", className)} data-testid="fact-chip">
      <span className="label-mono truncate text-muted">{label}</span>
      <span className="fact-mark mt-0.5 w-fit max-w-full truncate text-sm font-semibold">{value}</span>
      <span className="mt-1 inline-flex min-w-0 items-center gap-1 text-[0.6875rem] text-muted">
        {source ? <FileText className="size-3 shrink-0" aria-hidden /> : <UserRound className="size-3 shrink-0" aria-hidden />}
        <span className="truncate">{source ? t("fromFile", { file: source }) : t("fromYou")}</span>
      </span>
    </li>
  );
}

/** Label for a fact key: translated when known, else the key made readable. */
export function useFactLabel() {
  const t = useTranslations("facts");
  return (key: string | null) => {
    if (!key) return t("verified");
    return t.has(`${key}.label`) ? t(`${key}.label`) : key.replace(/_/g, " ");
  };
}
