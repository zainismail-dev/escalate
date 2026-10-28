import { ArrowRight, BadgeCheck, FileSearch, Handshake, Lock, MessageSquareText, Scale, ShieldCheck, Upload } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { CaseChipStatic } from "@/components/landing/static-chip";
import { LocalPacks } from "@/components/landing/local-packs";
import { EscalationLadder } from "@/components/ladder";
import { Button } from "@/components/ui/button";
import { WhyPanel } from "@/components/why-panel";
import { formatDate, formatMoney } from "@/lib/format";
import type { LadderStep, Reason } from "@/lib/types";

/** Example values for the showcase. Formatting is Intl with each example's own locale. */
const EXAMPLES = [
  { locale: "en-PK", currency: "PKR", amount: 64500 },
  { locale: "en-IN", currency: "INR", amount: 18000 },
  { locale: "en-GB", currency: "GBP", amount: 39.99 },
  { locale: "de-DE", currency: "EUR", amount: 89.9 },
  { locale: "en-US", currency: "USD", amount: 1249 },
];
const EXAMPLE_DATE = "2026-10-28";
const URDU_SAMPLE = "یہ دستاویز Escalate (ایک مفت سیلف ہیلپ ٹول) سے تیار کی گئی ہے۔ یہ قانونی مشورہ نہیں ہے۔";

export default function Landing() {
  const t = useTranslations("landing");
  const steps: LadderStep[] = (["s1", "s2", "s3", "s4"] as const).map((id, i) => ({
    id,
    name: t(`ladder.${id}`),
    channel: ["email", "web_form", "post", "court"][i],
    recipient_role: null,
    wait_days: [5, 5, 15, null][i],
    state: i < 2 ? "done" : i === 2 ? "current" : "future",
  }));
  const reasons: Reason[] = [
    { code: "after_verdict", params: { verdict: "refused", step: t("ladder.s2") } },
    { code: "position", params: { n: 3, total: 4 } },
    { code: "channel", params: { channel: "post", recipient: t("showcase.recipient") } },
    { code: "wait", params: { days: 15 } },
    { code: "proof", params: { proof: t("showcase.proof") } },
  ];
  return (
    <>
      {/* Hero: always dark */}
      <section className="dark bg-night text-text">
        <div className="mx-auto grid max-w-6xl gap-10 px-4 pb-20 pt-14 md:grid-cols-[1.1fr_1fr] md:items-center md:pt-20">
          <div>
            <p className="label-mono text-lime">{t("hero.eyebrow")}</p>
            <h1 className="mt-4 font-display text-[2.6rem] font-extrabold leading-[1.02] tracking-[-0.03em] sm:text-6xl">
              {t("hero.title")}
            </h1>
            <p className="mt-5 max-w-xl text-lg text-text-2">{t("hero.body")}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button variant="lime" size="lg" asChild>
                <Link href="/cases/new">
                  {t("hero.cta")}
                  <ArrowRight className="rtl:rotate-180" aria-hidden />
                </Link>
              </Button>
              <Button size="lg" asChild>
                <Link href="/cases">{t("hero.secondary")}</Link>
              </Button>
            </div>
            <p className="mt-6 flex items-center gap-2 text-sm text-muted">
              <ShieldCheck className="size-4 text-lime" aria-hidden />
              {t("hero.approve")}
            </p>
          </div>
          <div className="rounded-3xl border border-night-line bg-night-card p-5 shadow-2xl sm:p-6" data-testid="hero-ladder">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="label-mono text-muted">{t("hero.caseLabel")}</p>
                <p className="mt-1 font-display text-xl">{t("hero.caseTitle")}</p>
              </div>
              <p className="font-mono text-2xl font-bold">{formatMoney(64500, "PKR", "en-PK")}</p>
            </div>
            <CaseChipStatic country="PK" currency="PKR" className="mt-3" />
            <EscalationLadder steps={steps} className="mt-6" />
            <div className="mt-5 rounded-xl bg-lime p-4 text-on-lime">
              <p className="label-mono font-bold">{t("hero.nextLabel")}</p>
              <p className="mt-1 font-semibold">{t("hero.next")}</p>
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="mx-auto max-w-6xl px-4 py-20" aria-labelledby="how">
        <p className="label-mono text-muted">{t("how.eyebrow")}</p>
        <h2 id="how" className="mt-2 font-display text-3xl sm:text-4xl">{t("how.title")}</h2>
        <ol className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[MessageSquareText, Upload, BadgeCheck, Scale].map((Icon, i) => (
            <li key={i} className="rounded-2xl border border-line bg-card p-5">
              <div className="flex items-center justify-between">
                <span className="grid size-10 place-items-center rounded-xl bg-lime text-on-lime">
                  <Icon className="size-5" aria-hidden />
                </span>
                <span className="label-mono text-muted">{String(i + 1).padStart(2, "0")}</span>
              </div>
              <h3 className="mt-4 font-display text-lg">{t(`how.s${i + 1}.title`)}</h3>
              <p className="mt-1 text-sm text-text-2">{t(`how.s${i + 1}.body`)}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* Agent reasoning showcase */}
      <section className="border-y border-line bg-card" aria-labelledby="showcase">
        <div className="mx-auto grid max-w-6xl gap-10 px-4 py-20 md:grid-cols-2 md:items-center">
          <div>
            <p className="label-mono text-muted">{t("showcase.eyebrow")}</p>
            <h2 id="showcase" className="mt-2 font-display text-3xl sm:text-4xl">{t("showcase.title")}</h2>
            <p className="mt-4 text-text-2">{t("showcase.body")}</p>
            <ul className="mt-6 space-y-3 text-sm">
              {["facts", "playbook", "deadlines"].map((k) => (
                <li key={k} className="flex gap-2">
                  <FileSearch className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />
                  {t(`showcase.points.${k}`)}
                </li>
              ))}
            </ul>
          </div>
          <WhyPanel reasons={reasons} playbook="pk-ecommerce-refund-refused" version="0.1.0" className="bg-bg" />
        </div>
      </section>

      {/* Global by design */}
      <section className="mx-auto max-w-6xl px-4 py-20" aria-labelledby="global">
        <p className="label-mono text-muted">{t("global.eyebrow")}</p>
        <h2 id="global" className="mt-2 font-display text-3xl sm:text-4xl">{t("global.title")}</h2>
        <p className="mt-4 max-w-2xl text-text-2">{t("global.body")}</p>
        <div className="mt-10 grid gap-4 lg:grid-cols-[1.3fr_1fr]">
          <div className="rounded-2xl border border-line bg-card p-5">
            <p className="label-mono text-muted">{t("global.formatTitle")}</p>
            <ul className="mt-4 divide-y divide-line">
              {EXAMPLES.map((e) => (
                <li key={e.locale} className="flex flex-wrap items-baseline justify-between gap-2 py-3">
                  <span className="font-mono text-xs text-muted">
                    {e.locale} · {e.currency}
                  </span>
                  <span className="font-mono text-lg font-semibold" dir="ltr">
                    {formatMoney(e.amount, e.currency, e.locale)}
                  </span>
                  <span className="basis-full text-end text-sm text-text-2 sm:basis-auto">{formatDate(EXAMPLE_DATE, e.locale, "long")}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="space-y-4">
            <div className="rounded-2xl border border-line bg-card p-5">
              <p className="label-mono text-muted">{t("global.rtlTitle")}</p>
              <p lang="ur" dir="rtl" className="letter mt-3 rounded-md border border-line p-4 text-lg">
                {URDU_SAMPLE}
              </p>
              <p className="mt-2 text-xs text-muted">{t("global.rtlNote")}</p>
            </div>
            <div className="rounded-2xl border border-line bg-card p-5">
              <p className="label-mono text-muted">{t("global.packsTitle")}</p>
              <div className="mt-3">
                <LocalPacks />
              </div>
              <p className="mt-3 text-xs text-muted">{t("global.packsNote")}</p>
            </div>
          </div>
        </div>
      </section>

      {/* Safety */}
      <section className="border-t border-line bg-card" aria-labelledby="safety">
        <div className="mx-auto max-w-6xl px-4 py-20">
          <p className="label-mono text-muted">{t("safety.eyebrow")}</p>
          <h2 id="safety" className="mt-2 font-display text-3xl sm:text-4xl">{t("safety.title")}</h2>
          <ul className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              [Handshake, "approve"],
              [BadgeCheck, "facts"],
              [Lock, "private"],
              [Scale, "legal"],
            ].map(([Icon, k]) => {
              const I = Icon as typeof Lock;
              return (
                <li key={k as string} className="rounded-2xl border border-line bg-bg p-5">
                  <I className="size-6" aria-hidden />
                  <h3 className="mt-3 font-display text-lg">{t(`safety.${k}.title`)}</h3>
                  <p className="mt-1 text-sm text-text-2">{t(`safety.${k}.body`)}</p>
                </li>
              );
            })}
          </ul>
        </div>
      </section>

      {/* CTA */}
      <section className="dark bg-night text-text">
        <div className="mx-auto flex max-w-6xl flex-col items-start gap-6 px-4 py-16 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="font-display text-3xl sm:text-4xl">{t("cta.title")}</h2>
            <p className="mt-2 text-text-2">{t("cta.body")}</p>
          </div>
          <Button variant="lime" size="lg" asChild>
            <Link href="/cases/new">
              {t("hero.cta")}
              <ArrowRight className="rtl:rotate-180" aria-hidden />
            </Link>
          </Button>
        </div>
        <footer className="border-t border-night-line">
          <div className="mx-auto max-w-6xl px-4 py-6 pb-24 text-xs text-muted md:pb-6">{t("footer")}</div>
        </footer>
      </section>
    </>
  );
}
