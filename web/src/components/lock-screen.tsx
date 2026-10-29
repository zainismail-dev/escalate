"use client";
import { Loader2, LockKeyhole } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { FieldHint, Input, Label } from "@/components/ui/input";
import { api, ApiError, LOCKED_EVENT } from "@/lib/api";

/** The optional app lock (APP_PASSCODE on the API). Without it the API never answers "locked"
 * and this renders its children unchanged. */
export function LockGate({ children }: { children: React.ReactNode }) {
  const [locked, setLocked] = useState(false);
  const [generation, setGeneration] = useState(0);

  useEffect(() => {
    const lock = () => setLocked(true);
    window.addEventListener(LOCKED_EVENT, lock);
    api
      .lockStatus()
      .then((s) => setLocked(s.enabled && !s.unlocked))
      .catch(() => {}); // an unreachable API shows its own error state
    return () => window.removeEventListener(LOCKED_EVENT, lock);
  }, []);

  if (locked)
    return (
      <LockScreen
        onUnlocked={() => {
          setLocked(false);
          setGeneration((g) => g + 1); // remount the page so it reloads its data
        }}
      />
    );
  return <div key={generation}>{children}</div>;
}

function LockScreen({ onUnlocked }: { onUnlocked: () => void }) {
  const t = useTranslations("lock");
  const [passcode, setPasscode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.unlock(passcode);
      onUnlocked();
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      setError(status === 401 ? t("wrong") : status === 429 ? t("tooMany") : t("failed"));
    } finally {
      setBusy(false);
      setPasscode("");
    }
  }

  return (
    <div className="mx-auto max-w-sm py-16" data-testid="lock-screen">
      <form onSubmit={submit} className="space-y-4 rounded-2xl border border-line bg-card p-6">
        <div className="flex items-center gap-2">
          <LockKeyhole className="size-5" aria-hidden />
          <h1 className="font-display text-xl">{t("title")}</h1>
        </div>
        <p className="text-sm text-text-2">{t("body")}</p>
        <div className="space-y-1.5">
          <Label htmlFor="passcode">{t("label")}</Label>
          <Input
            id="passcode"
            type="password"
            autoComplete="current-password"
            value={passcode}
            onChange={(e) => setPasscode(e.target.value)}
            aria-invalid={!!error}
            aria-describedby={error ? "passcode-error" : undefined}
            autoFocus
          />
          {error && (
            <FieldHint id="passcode-error" className="text-danger" role="alert">
              {error}
            </FieldHint>
          )}
        </div>
        <Button type="submit" variant="lime" className="w-full" disabled={!passcode || busy}>
          {busy && <Loader2 className="animate-spin" aria-hidden />}
          {t("unlock")}
        </Button>
      </form>
    </div>
  );
}
