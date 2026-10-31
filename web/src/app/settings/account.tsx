"use client";
/** Hosted beta: the account card on Settings (usage, export, delete). */
import { Download, Trash2, UserRound } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/input";
import { api } from "@/lib/api";
import { signOut } from "@/lib/auth";
import { useAction, useApi } from "@/lib/use-api";

export function AccountSection() {
  const t = useTranslations("hosted.account");
  const tc = useTranslations("common");
  const router = useRouter();
  const me = useApi(() => api.me(), []);
  const act = useAction();
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <UserRound className="size-5" aria-hidden />
          {t("title")}
        </CardTitle>
        {me.data && <p className="text-sm text-text-2">{t("signedInAs", { email: me.data.email })}</p>}
      </CardHeader>
      <CardContent className="space-y-4">
        {me.data && (
          <ul className="space-y-1 text-sm text-text-2" data-testid="usage">
            <li>{t("openCases", { n: me.data.open_cases, max: me.data.max_open_cases })}</li>
            <li>{t("aiCalls", { n: me.data.ai_calls_today, max: me.data.ai_calls_per_day })}</li>
          </ul>
        )}
        <p className="text-sm text-text-2">{t("where")}</p>
        <div className="flex flex-wrap gap-2">
          <Button disabled={act.busy} onClick={() => act.run(() => api.downloadAccountExport())}>
            <Download aria-hidden />
            {t("export")}
          </Button>
          <Button variant="ghost" asChild>
            <Link href="/privacy">{t("privacy")}</Link>
          </Button>
          <Button variant="ghost" asChild>
            <Link href="/terms">{t("terms")}</Link>
          </Button>
        </div>
        <div className="rounded-xl border border-danger/40 bg-danger-bg p-4">
          <p className="font-semibold text-text">{t("deleteTitle")}</p>
          <p className="mt-1 text-sm text-text-2">{t("deleteBody")}</p>
          <Button variant="danger" className="mt-3" onClick={() => setOpen(true)}>
            <Trash2 aria-hidden />
            {t("deleteCta")}
          </Button>
        </div>
        {act.error && <ErrorState error={act.error} />}
      </CardContent>
      <Dialog open={open} onOpenChange={(o) => (setOpen(o), setTyped(""))}>
        <DialogContent closeLabel={tc("close")}>
          <DialogTitle>{t("confirmTitle")}</DialogTitle>
          <DialogDescription>{t("confirmBody")}</DialogDescription>
          <div className="mt-4 space-y-1.5">
            <Label htmlFor="type-delete">{t("typeDelete")}</Label>
            <Input id="type-delete" autoComplete="off" value={typed} onChange={(e) => setTyped(e.target.value)} />
          </div>
          <div className="mt-6 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="danger"
              disabled={typed !== "DELETE" || act.busy}
              onClick={async () => {
                const ok = await act.run(async () => {
                  await api.deleteAccount();
                  return true;
                });
                setOpen(false);
                if (ok) {
                  await signOut();
                  router.replace("/signin?deleted=1");
                }
              }}
            >
              {t("deleteCta")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
