import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { CaseQuestions } from "./view";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("questions"))("metaTitle") };
}

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <CaseQuestions id={Number(id)} />;
}
