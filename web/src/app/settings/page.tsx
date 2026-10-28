import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { SettingsView } from "./view";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("settings"))("title") };
}

export default function SettingsPage() {
  return <SettingsView />;
}
