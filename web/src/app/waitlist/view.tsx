"use client";
import { Hourglass } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { signOut } from "@/lib/auth";

export function Waitlist() {
  const t = useTranslations("hosted.waitlist");
  const th = useTranslations("hosted");
  const router = useRouter();
  const [email, setEmail] = useState("");
  useEffect(() => {
    api
      .me()
      .then((me) => (me.invited ? router.replace(me.consented ? "/cases" : "/welcome") : setEmail(me.email)))
      .catch(() => {});
  }, [router]);
  return (
    <div className="mx-auto max-w-md py-16 text-center" data-testid="waitlist">
      <Hourglass className="mx-auto size-10 text-muted" aria-hidden />
      <h1 className="mt-4 font-display text-3xl">{t("title")}</h1>
      <p className="mt-3 text-text-2">{t("body", { email: email || "…" })}</p>
      <p className="mt-3 text-sm text-muted">{t("noData")}</p>
      <Button
        className="mt-6"
        variant="ink"
        onClick={async () => {
          await signOut();
          router.replace("/signin");
        }}
      >
        {th("signOut")}
      </Button>
    </div>
  );
}
