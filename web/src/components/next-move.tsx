"use client";
import { ArrowRight, FileDown, Upload } from "lucide-react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { CaseDetail } from "@/lib/types";

/** "Your next move": one clear action, with a lime call to action. */
export function NextMove({ c, onDeliveryUpload }: { c: CaseDetail; onDeliveryUpload?: () => void }) {
  const t = useTranslations("nextMove");
  const locale = useLocale();
  const w = c.waiting_for;
  let key: string = w ?? (["resolved", "closed_unresolved", "withdrawn"].includes(c.status) ? c.status : "none");
  if (!w && c.status === "intake") key = "start";
  const href: Record<string, string> = {
    approve_draft: `/cases/${c.id}/review`,
    questions: `/cases/${c.id}/questions`,
    urgent_checklist: `/cases/${c.id}/urgent`,
    waiting_reply: `/cases/${c.id}/reply`,
    confirm_resolution: `/cases/${c.id}/reply`,
    start: `/cases/new?case=${c.id}`,
  };
  const when = c.next_action_at ? (formatDateTime(c.next_action_at, locale) ?? "") : "";
  return (
    <section aria-labelledby="next-move" className="rounded-2xl border border-line bg-card p-5" data-testid="next-move">
      <p className="label-mono text-muted">{t("title")}</p>
      <h2 id="next-move" className="mt-1 font-display text-xl">{t(`${key}.title`)}</h2>
      <p className="mt-1 text-sm text-text-2">{t(`${key}.body`, { when, step: c.step_name ?? "" })}</p>
      <div className="mt-4 flex flex-wrap gap-2">
        {href[key] && (
          <Button variant="lime" size="lg" asChild>
            <Link href={href[key]}>
              {t(`${key}.cta`)}
              <ArrowRight className="rtl:rotate-180" aria-hidden />
            </Link>
          </Button>
        )}
        {key === "confirm_delivery" && c.pending?.message_id && (
          <>
            <Button variant="lime" size="lg" asChild>
              <a href={api.printableUrl(c.pending.message_id)}>
                <FileDown aria-hidden />
                {t("confirm_delivery.print")}
              </a>
            </Button>
            <Button size="lg" onClick={onDeliveryUpload}>
              <Upload aria-hidden />
              {t("confirm_delivery.cta")}
            </Button>
          </>
        )}
      </div>
    </section>
  );
}
