"use client";
/** The hosted beta's chrome: the sign-in gate, "Waking the server…", the signed-in email with
 * Sign out, and links that download from the API with the sign-in token. Self-hosted and demo
 * builds never render these (HOSTED is false at build time). */
import { Loader2, LogOut } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
import { onAuthChange, signedInEmail, signOut } from "@/lib/auth";
import { CONSENT_EVENT, PUBLIC_PATHS, SIGNED_OUT_EVENT, WAITLIST_EVENT, WAKING_EVENT } from "@/lib/hosted";

const DOWNLOAD_FAILED = "escalate:download-failed";
const SIGNED_IN_ONLY = ["/waitlist", "/welcome"]; // these pages check the invite themselves
let memberChecked = false; // invited and consented, checked once per page load

export function HostedGate({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const open = PUBLIC_PATHS.includes(path);
  const [ready, setReady] = useState(open || memberChecked);

  useEffect(() => {
    const go = (to: string) => () => {
      memberChecked = false;
      router.replace(to);
    };
    const handlers: [string, () => void][] = [
      [SIGNED_OUT_EVENT, go("/signin")],
      [WAITLIST_EVENT, go("/waitlist")],
      [CONSENT_EVENT, go("/welcome")],
    ];
    for (const [e, h] of handlers) window.addEventListener(e, h);
    return () => handlers.forEach(([e, h]) => window.removeEventListener(e, h));
  }, [router]);

  useEffect(() => {
    if (open || memberChecked) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setReady(true);
      return;
    }
    let cancelled = false;
    setReady(false);
    (async () => {
      if (!(await signedInEmail())) return router.replace(`/signin?next=${encodeURIComponent(path)}`);
      if (SIGNED_IN_ONLY.includes(path)) return !cancelled && setReady(true);
      try {
        const me = await api.me();
        if (!me.invited) return router.replace("/waitlist");
        if (!me.consented) return router.replace("/welcome");
        memberChecked = true;
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return router.replace("/signin");
        // anything else (API down): let the page show its own error state
      }
      if (!cancelled) setReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [open, path, router]);

  if (!ready) return <Checking />;
  return <>{children}</>;
}

function Checking() {
  const t = useTranslations("hosted");
  return (
    <div className="flex items-center justify-center gap-2 py-24 text-sm text-text-2" role="status">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {t("checking")}
    </div>
  );
}

/** "Waking the server…" while the free API boots, and download errors. */
export function HostedNotices() {
  const t = useTranslations("hosted");
  const [waking, setWaking] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  useEffect(() => {
    const onWake = (e: Event) => setWaking(Boolean((e as CustomEvent<boolean>).detail));
    const onFail = (e: Event) => setFailed(String((e as CustomEvent<string>).detail));
    window.addEventListener(WAKING_EVENT, onWake);
    window.addEventListener(DOWNLOAD_FAILED, onFail);
    return () => {
      window.removeEventListener(WAKING_EVENT, onWake);
      window.removeEventListener(DOWNLOAD_FAILED, onFail);
    };
  }, []);
  return (
    <>
      {waking && (
        <div role="status" className="flex items-center justify-center gap-2 border-b border-line bg-info-bg px-4 py-2 text-xs font-semibold text-info" data-testid="waking">
          <Loader2 className="size-3.5 animate-spin" aria-hidden />
          {t("waking")}
        </div>
      )}
      {failed && (
        <div role="alert" className="flex items-center justify-center gap-3 border-b border-line bg-danger-bg px-4 py-2 text-xs text-danger">
          {t("downloadFailed", { detail: failed })}
          <button type="button" className="font-semibold underline" onClick={() => setFailed(null)}>
            {t("dismiss")}
          </button>
        </div>
      )}
    </>
  );
}

/** The signed-in email and Sign out (or a Sign in link). */
export function AccountMenu() {
  const t = useTranslations("hosted");
  const router = useRouter();
  const [email, setEmail] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    let unsubscribe = () => {};
    void signedInEmail().then(setEmail);
    void onAuthChange(setEmail).then((u) => (unsubscribe = u));
    return () => unsubscribe();
  }, []);
  if (email === undefined) return null;
  if (!email)
    return (
      <Button size="sm" variant="ink" asChild>
        <Link href="/signin">{t("signIn")}</Link>
      </Button>
    );
  return (
    <div className="flex items-center gap-1">
      <span className="hidden max-w-48 truncate text-xs text-text-2 sm:inline" data-testid="signed-in-email" title={email}>
        {email}
      </span>
      <Button
        size="sm"
        variant="ghost"
        onClick={async () => {
          memberChecked = false;
          await signOut();
          router.replace("/signin");
        }}
      >
        <LogOut aria-hidden />
        <span className="sr-only sm:not-sr-only">{t("signOut")}</span>
      </Button>
    </div>
  );
}

/** A file from the API: a plain link in self-hosted builds; hosted, a fetch with the token. */
export function FileLink({ href, hosted, download, className, children }: {
  href: string;
  hosted: boolean;
  download: () => Promise<void>;
  className?: string;
  children: React.ReactNode;
}) {
  if (!hosted) return <a href={href} className={className}>{children}</a>;
  return (
    <a
      href={href}
      className={className}
      onClick={(e) => {
        e.preventDefault();
        download().catch((err: unknown) =>
          window.dispatchEvent(new CustomEvent(DOWNLOAD_FAILED, { detail: err instanceof ApiError ? err.detail : String(err) })),
        );
      }}
    >
      {children}
    </a>
  );
}
