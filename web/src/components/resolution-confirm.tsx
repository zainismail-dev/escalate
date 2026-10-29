"use client";
import { CheckCircle2, ShieldQuestion } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Label, NativeSelect } from "@/components/ui/input";
import { api } from "@/lib/api";

const OTHER = ["refused", "partial", "no_reply"] as const;

/**
 * The agent judged a reply "resolved". A reply can be written to fool the model, so the case
 * only closes when the user confirms they really got what they asked for.
 */
export function ResolutionConfirm({ caseId, reason, onDone }: { caseId: string; reason?: string | null; onDone: () => void }) {
  const t = useTranslations("reply.confirmResolution");
  const tv = useTranslations("verdict");
  const [verdict, setVerdict] = useState<(typeof OTHER)[number]>("refused");
  const [busy, setBusy] = useState(false);
  const run = async (resolved: boolean) => {
    setBusy(true);
    try {
      await api.confirmResolution(caseId, resolved, resolved ? undefined : verdict);
      onDone();
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="rounded-2xl border-[1.5px] border-line-strong bg-card p-5" aria-labelledby="confirm-resolution" data-testid="confirm-resolution">
      <h2 id="confirm-resolution" className="flex items-center gap-2 font-display text-xl">
        <ShieldQuestion className="size-5" aria-hidden />
        {t("title")}
      </h2>
      <p className="mt-1 text-sm text-text-2">{t("body")}</p>
      {reason && <p className="mt-2 rounded-xl bg-raised p-3 text-sm text-text-2">{reason}</p>}
      <div className="mt-4 flex flex-wrap items-end gap-3">
        <Button variant="lime" disabled={busy} onClick={() => run(true)} data-testid="confirm-resolved">
          <CheckCircle2 aria-hidden />
          {t("yes")}
        </Button>
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <Label htmlFor="not-resolved-verdict" className="text-xs">
              {t("notResolvedLabel")}
            </Label>
            <NativeSelect id="not-resolved-verdict" value={verdict} onChange={(e) => setVerdict(e.target.value as (typeof OTHER)[number])} className="w-auto">
              {OTHER.map((v) => (
                <option key={v} value={v}>
                  {tv(v)}
                </option>
              ))}
            </NativeSelect>
          </div>
          <Button disabled={busy} onClick={() => run(false)} data-testid="deny-resolved">
            {t("no")}
          </Button>
        </div>
      </div>
    </section>
  );
}
