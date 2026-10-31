"use client";
/** Google sends the user back here with a one-time code; the Supabase client exchanges it
 * (PKCE) for a session, then the app continues where the user was going. */
import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { supabase } from "@/lib/auth";

export function Callback() {
  const t = useTranslations("hosted.callback");
  const router = useRouter();
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let done = false;
    (async () => {
      const sb = await supabase();
      const code = new URLSearchParams(window.location.search).get("code");
      if (!sb || !code) return setFailed(true);
      const { data } = await sb.auth.getSession(); // detectSessionInUrl may have exchanged it
      if (!data.session) {
        const { error } = await sb.auth.exchangeCodeForSession(code);
        if (error) return setFailed(true);
      }
      if (done) return;
      const next = sessionStorage.getItem("escalate:next");
      sessionStorage.removeItem("escalate:next");
      router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/cases");
    })();
    return () => {
      done = true;
    };
  }, [router]);
  return (
    <div className="mx-auto max-w-sm py-16 text-center" role="status">
      {failed ? (
        <>
          <p className="text-text-2">{t("failed")}</p>
          <Button className="mt-4" variant="ink" asChild>
            <Link href="/signin">{t("retry")}</Link>
          </Button>
        </>
      ) : (
        <p className="inline-flex items-center gap-2 text-text-2">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          {t("working")}
        </p>
      )}
    </div>
  );
}
