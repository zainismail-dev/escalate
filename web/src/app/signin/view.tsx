"use client";
import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Suspense, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { signedInEmail, signInWithGoogle } from "@/lib/auth";
import { SUPABASE_ANON_KEY, SUPABASE_URL } from "@/lib/hosted";

function GoogleMark() {
  return (
    <svg viewBox="0 0 48 48" className="size-5" aria-hidden>
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 38.3 44 33 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  );
}

function SignInInner() {
  const t = useTranslations("hosted.signin");
  const th = useTranslations("hosted");
  const router = useRouter();
  const params = useSearchParams();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const configured = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
  const next = params.get("next");
  const target = next && next.startsWith("/") && !next.startsWith("//") ? next : "/cases";

  useEffect(() => {
    void signedInEmail().then((email) => email && router.replace(target));
  }, [router, target]);

  return (
    <div className="mx-auto max-w-sm py-16 text-center" data-testid="signin">
      <h1 className="font-display text-3xl">{t("title")}</h1>
      <p className="mt-2 text-text-2">{t("body")}</p>
      {params.get("deleted") && (
        <p role="status" className="mt-4 rounded-xl bg-success-bg p-3 text-sm text-success">
          {t("deleted")}
        </p>
      )}
      <Button
        size="lg"
        variant="ink"
        className="mt-6 w-full"
        disabled={busy || !configured}
        onClick={async () => {
          setBusy(true);
          setFailed(false);
          try {
            sessionStorage.setItem("escalate:next", target);
            await signInWithGoogle(); // leaves the page for Google
          } catch {
            setFailed(true);
            setBusy(false);
          }
        }}
      >
        {busy ? <Loader2 className="animate-spin" aria-hidden /> : <GoogleMark />}
        {busy ? t("busy") : t("google")}
      </Button>
      {!configured && <p className="mt-3 text-sm text-danger">{t("notConfigured")}</p>}
      {failed && <p role="alert" className="mt-3 text-sm text-danger">{t("failed")}</p>}
      <p className="mt-6 text-xs text-muted">
        {t("agree")}{" "}
        <Link className="underline" href="/terms">{th("terms")}</Link> ·{" "}
        <Link className="underline" href="/privacy">{th("privacy")}</Link>
      </p>
    </div>
  );
}

export function SignIn() {
  return (
    <Suspense>
      <SignInInner />
    </Suspense>
  );
}
