"use client";
import { Info } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useFactLabel } from "@/components/fact-chip";
import { Button } from "@/components/ui/button";
import { FieldHint, Input, Label } from "@/components/ui/input";
import { inputTypeFor } from "@/lib/facts";

/** The agent's missing-fact questions, each with "why we ask". Never asks for secrets. */
export function QuestionsForm({ missing, busy, onSubmit }: { missing: string[]; busy: boolean; onSubmit: (a: Record<string, string>) => void }) {
  const t = useTranslations("questions");
  const tf = useTranslations("facts");
  const label = useFactLabel();
  const [values, setValues] = useState<Record<string, string>>({});
  const filled = missing.filter((k) => (values[k] || "").trim()).length;
  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(values);
      }}
    >
      <p className="text-sm text-text-2">{t("intro", { count: missing.length })}</p>
      {missing.map((key) => {
        const id = `q-${key}`;
        return (
          <div key={key} className="space-y-1.5 rounded-xl border border-line bg-card p-4">
            <Label htmlFor={id}>{label(key)}</Label>
            <Input
              id={id}
              name={key}
              type={inputTypeFor(key)}
              value={values[key] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))}
              aria-describedby={`${id}-why`}
              autoComplete="off"
            />
            <FieldHint id={`${id}-why`} className="flex gap-1.5">
              <Info className="mt-px size-3.5 shrink-0" aria-hidden />
              <span>
                <span className="font-semibold text-text-2">{t("why")}</span>{" "}
                {tf.has(`${key}.why`) ? tf(`${key}.why`) : t("whyDefault")}
              </span>
            </FieldHint>
          </div>
        );
      })}
      <p className="rounded-xl bg-info-bg p-3 text-xs text-info">{t("noSecrets")}</p>
      <Button type="submit" variant="lime" size="lg" disabled={busy || filled === 0}>
        {t("submit", { filled, total: missing.length })}
      </Button>
    </form>
  );
}
