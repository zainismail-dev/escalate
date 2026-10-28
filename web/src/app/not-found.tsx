import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { Button } from "@/components/ui/button";

export default async function NotFound() {
  const t = await getTranslations("notFound");
  return (
    <div className="mx-auto max-w-md py-16 text-center">
      <p className="label-mono text-muted">404</p>
      <h1 className="mt-2 font-display text-3xl">{t("title")}</h1>
      <p className="mt-2 text-text-2">{t("body")}</p>
      <Button variant="lime" className="mt-6" asChild>
        <Link href="/cases">{t("cta")}</Link>
      </Button>
    </div>
  );
}
