import { getTranslations } from "next-intl/server";

/** The hosted beta's privacy policy and terms: plain templates, filled with the operator's name
 * and contact address from NEXT_PUBLIC_OPERATOR_NAME and NEXT_PUBLIC_CONTACT_EMAIL. */
export async function LegalPage({ ns, sections }: { ns: "hosted.privacyPage" | "hosted.termsPage"; sections: readonly string[] }) {
  const t = await getTranslations(ns);
  const tl = await getTranslations("hosted.legal");
  const operator = process.env.NEXT_PUBLIC_OPERATOR_NAME || tl("operator");
  const contact = process.env.NEXT_PUBLIC_CONTACT_EMAIL || tl("noContact");
  const values = { operator, contact };
  return (
    <article className="mx-auto max-w-2xl space-y-6 py-6">
      <header>
        <h1 className="font-display text-3xl">{t("title")}</h1>
        <p className="mt-2 text-text-2">{t("intro", values)}</p>
        {!process.env.NEXT_PUBLIC_CONTACT_EMAIL && (
          <p className="mt-3 rounded-xl bg-warning-bg p-3 text-sm text-warning">{tl("template")}</p>
        )}
      </header>
      {sections.map((s) => (
        <section key={s}>
          <h2 className="font-display text-xl">{t(`${s}Title`)}</h2>
          <p className="mt-1 text-text-2">{t(s, values)}</p>
        </section>
      ))}
    </article>
  );
}
