import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { CasesList } from "./cases-list";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("cases"))("title") };
}

export default function CasesPage() {
  return <CasesList />;
}
