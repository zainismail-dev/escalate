"use client";
/** Hosted beta, after approval: the user sends the letter from their own mailbox. Escalate never
 * sends email there; "I've sent it" records the send (sent_by: user). */
import { CheckCircle2, Copy, FileDown, Mail } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { FileLink } from "@/components/hosted";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { letterText, mailtoHref } from "@/lib/mailto";
import type { CaseDetail } from "@/lib/types";
import { useAction } from "@/lib/use-api";

export function HostedSend({ c, onSent }: { c: CaseDetail; onSent: () => void }) {
  const t = useTranslations("hosted.send");
  const act = useAction();
  const [copied, setCopied] = useState(false);
  const msg = c.messages.find((m) => m.id === c.pending?.message_id);
  if (!msg) return null;
  const { href, bodyIncluded } = mailtoHref(msg.recipient, msg.subject, msg.body);
  return (
    <div className="mt-4 space-y-3" data-testid="hosted-send">
      <p className="text-sm text-text-2">{t("intro", { recipient: msg.recipient ?? "" })}</p>
      {!bodyIncluded && <p className="rounded-xl bg-warning-bg p-3 text-sm text-warning">{t("tooLong")}</p>}
      <div className="flex flex-wrap gap-2">
        <Button variant="lime" size="lg" asChild>
          <a href={href} data-testid="mailto">
            <Mail aria-hidden />
            {t("open")}
          </a>
        </Button>
        <Button
          size="lg"
          onClick={async () => {
            await navigator.clipboard.writeText(letterText(msg.subject, msg.body));
            setCopied(true);
          }}
        >
          <Copy aria-hidden />
          {copied ? t("copied") : t("copy")}
        </Button>
        <Button size="lg" asChild>
          <FileLink href={api.printableUrl(msg.id)} hosted download={() => api.downloadLetterPdf(msg.id)}>
            <FileDown aria-hidden />
            {t("pdf")}
          </FileLink>
        </Button>
      </div>
      <div className="rounded-xl border border-line p-4">
        <p className="text-sm text-text-2">{t("confirmHint")}</p>
        <Button
          className="mt-3"
          variant="ink"
          disabled={act.busy}
          onClick={async () => {
            const done = await act.run(() => api.confirmDelivery(msg.id));
            if (done) onSent();
          }}
        >
          <CheckCircle2 aria-hidden />
          {t("sent")}
        </Button>
      </div>
      {act.error && <ErrorState error={act.error} />}
    </div>
  );
}
