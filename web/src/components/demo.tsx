"use client";
import { ExternalLink, FlaskConical, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { RepoLink } from "@/components/repo-link";
import { DEMO_LINK, DEMO_STATIC, DEMO_WRITE_EVENT, REPO_URL } from "@/lib/demo-mode";

/** The live demo's "nothing is saved or sent" dialog. Renders nothing elsewhere. */
export function DemoChrome() {
  if (!DEMO_STATIC) return null;
  return <DemoChromeInner />;
}

/** The permanent banner, inside the sticky header so it never scrolls away. */
export function DemoBanner() {
  const t = useTranslations("demo");
  if (!DEMO_STATIC) return null;
  return (
    <div className="border-b border-lime/40 bg-lime px-4 py-1.5 text-center text-xs font-semibold text-on-lime" role="note" data-testid="demo-banner">
      <FlaskConical className="me-1.5 inline size-3.5 align-[-2px]" aria-hidden />
      {t("banner")}
      <span aria-hidden> · </span>
      <RepoLink className="inline-flex [&_svg]:size-3.5" />
    </div>
  );
}

function DemoChromeInner() {
  const t = useTranslations("demo");
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const show = () => setOpen(true);
    // PDF links point at DEMO_LINK in the demo: open the dialog instead of navigating.
    const onClick = (e: MouseEvent) => {
      const a = (e.target as Element | null)?.closest?.("a");
      if (a?.getAttribute("href") === DEMO_LINK) {
        e.preventDefault();
        show();
      }
    };
    window.addEventListener(DEMO_WRITE_EVENT, show);
    document.addEventListener("click", onClick);
    return () => {
      window.removeEventListener(DEMO_WRITE_EVENT, show);
      document.removeEventListener("click", onClick);
    };
  }, []);

  return (
    <>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent closeLabel={t("close")} data-testid="demo-dialog">
          <DialogTitle>{t("dialogTitle")}</DialogTitle>
          <DialogDescription>{t("dialogBody")}</DialogDescription>
          <p className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-raised px-2.5 py-1 text-xs font-semibold text-success">
            <ShieldCheck className="size-3.5" aria-hidden />
            {t("nothingSent")}
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <Button variant="lime" asChild>
              <a href={REPO_URL} target="_blank" rel="noreferrer noopener">
                {t("getIt")}
                <ExternalLink aria-hidden />
              </a>
            </Button>
            <Button variant="outline" onClick={() => setOpen(false)}>
              {t("keepLooking")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

/** Where the new case wizard stops in the live demo (no agent, no model). */
export function DemoEnd() {
  const t = useTranslations("demo");
  return (
    <div className="rounded-2xl border-[1.5px] border-line-strong bg-card p-6 text-center" data-testid="demo-end">
      <FlaskConical className="mx-auto size-8 text-muted" aria-hidden />
      <h2 className="mt-2 font-display text-2xl">{t("endTitle")}</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-text-2">{t("endBody")}</p>
      <div className="mt-5 flex flex-wrap justify-center gap-2">
        <Button variant="lime" asChild>
          <a href={REPO_URL} target="_blank" rel="noreferrer noopener">
            {t("getIt")}
            <ExternalLink aria-hidden />
          </a>
        </Button>
        <Button variant="outline" asChild>
          <Link href="/cases">{t("seeCases")}</Link>
        </Button>
      </div>
    </div>
  );
}
