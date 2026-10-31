"use client";
/** The first-run consent: shown once, before the first case. */
import { CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useAction } from "@/lib/use-api";

const POINTS = ["ai", "legal", "own", "beta", "send"] as const;

export function Welcome() {
  const t = useTranslations("hosted.welcome");
  const router = useRouter();
  const act = useAction();
  return (
    <div className="mx-auto max-w-xl py-10" data-testid="welcome">
      <h1 className="font-display text-3xl">{t("title")}</h1>
      <p className="mt-2 text-text-2">{t("intro")}</p>
      <ul className="mt-6 space-y-3">
        {POINTS.map((k) => (
          <li key={k} className="flex gap-3 rounded-xl border border-line bg-card p-4 text-sm text-text-2">
            <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
            {t(k)}
          </li>
        ))}
      </ul>
      <p className="mt-4 text-sm">
        <Link className="underline" href="/privacy">
          {t("read")}
        </Link>
      </p>
      <Button
        size="lg"
        variant="lime"
        className="mt-6"
        disabled={act.busy}
        onClick={async () => {
          const me = await act.run(() => api.consent());
          if (me?.consented) router.replace("/cases");
        }}
      >
        {t("accept")}
      </Button>
      {act.error && <ErrorState className="mt-4" error={act.error} />}
    </div>
  );
}
