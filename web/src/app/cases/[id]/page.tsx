import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { CaseDashboard } from "./dashboard";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  return { title: (await getTranslations("dashboard"))("metaTitle", { id }) };
}

export default async function CasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <CaseDashboard id={Number(id)} />;
}
