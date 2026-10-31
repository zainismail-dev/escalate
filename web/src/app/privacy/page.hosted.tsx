import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { LegalPage } from "@/components/legal-page";

const SECTIONS = ["what", "why", "ai", "processors", "region", "retention", "rights", "security", "contact"] as const;

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("hosted.privacyPage"))("title") };
}

export default function PrivacyPage() {
  return <LegalPage ns="hosted.privacyPage" sections={SECTIONS} />;
}
