"use client";
import { AlertTriangle, AtSign, Pencil } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import type { RecipientCheck } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * The user confirms the exact recipient before approving. A recipient read from evidence may
 * have been planted there (prompt injection), so the agent's word is never enough.
 */
export function RecipientConfirm({
  check,
  messageId,
  checked,
  onChecked,
  onChanged,
}: {
  check: RecipientCheck;
  messageId: number;
  checked: boolean;
  onChecked: (v: boolean) => void;
  onChanged: () => void;
}) {
  const t = useTranslations("review.recipient");
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(check.recipient ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!check.recipient) return null;
  const source =
    check.source === "evidence"
      ? t("fromEvidence", { file: check.source_filename ?? "" })
      : check.source === "you"
        ? t("fromYou")
        : t("fromAgent");
  return (
    <div className={cn("mt-4 rounded-xl border p-3", check.changed ? "border-warning bg-warning-bg" : "border-line bg-raised")} data-testid="recipient-confirm">
      <p className="label-mono text-muted">{t("label")}</p>
      {editing ? (
        <form
          className="mt-1.5 flex gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            try {
              await api.setRecipient(messageId, value);
              setEditing(false);
              onChanged();
            } catch (err) {
              setError(err instanceof Error ? err.message : String(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          <label htmlFor="recipient-input" className="sr-only">
            {t("label")}
          </label>
          <Input id="recipient-input" value={value} onChange={(e) => setValue(e.target.value)} className="h-9 flex-1" autoFocus />
          <Button type="submit" size="sm" variant="ink" disabled={busy || !value.trim()}>
            {t("save")}
          </Button>
        </form>
      ) : (
        <div className="mt-1 flex items-start gap-2">
          <AtSign className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />
          <p className="min-w-0 flex-1 break-all font-semibold" data-testid="recipient-value">
            {check.recipient}
          </p>
          <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => setEditing(true)} aria-label={t("change")}>
            <Pencil aria-hidden />
          </Button>
        </div>
      )}
      {error && <p role="alert" className="mt-1 text-xs text-danger">{error}</p>}
      <p className="mt-1 text-xs text-muted">{source}</p>
      {check.changed && (
        <p role="alert" className="mt-2 flex gap-1.5 text-xs font-semibold text-warning" data-testid="recipient-changed">
          <AlertTriangle className="size-3.5 shrink-0" aria-hidden />
          {t("changed", { previous: check.previous ?? "" })}
        </p>
      )}
      <label className="mt-3 flex cursor-pointer items-start gap-2 text-sm">
        <Checkbox checked={checked} onCheckedChange={(v) => onChecked(v === true)} aria-describedby="recipient-hint" data-testid="recipient-checkbox" />
        <span>
          {t("confirm")}
          <span id="recipient-hint" className="block text-xs text-muted">
            {t("hint")}
          </span>
        </span>
      </label>
    </div>
  );
}
