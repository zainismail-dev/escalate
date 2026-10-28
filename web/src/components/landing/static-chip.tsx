import { useLocale } from "next-intl";
import { countryName, flag } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Server-rendered version of the case chip for the landing page: country · currency. */
export function CaseChipStatic({ country, currency, className }: { country: string; currency: string; className?: string }) {
  const ui = useLocale();
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border border-line bg-raised px-2.5 py-1 text-xs text-text-2", className)}>
      <span aria-hidden>{flag(country)}</span>
      <span className="font-semibold text-text">{countryName(country, ui)}</span>
      <span aria-hidden>·</span>
      <span className="font-mono text-[0.6875rem]">{currency}</span>
    </span>
  );
}
