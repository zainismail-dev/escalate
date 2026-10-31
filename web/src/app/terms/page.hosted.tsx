import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { LegalPage } from "@/components/legal-page";

const SECTIONS = ["what", "use", "beta", "liability", "end", "contact"] as const;

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("hosted.termsPage"))("title") };
}

export default function TermsPage() {
  return <LegalPage ns="hosted.termsPage" sections={SECTIONS} />;
}
