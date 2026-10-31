import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Welcome } from "./view";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("hosted.welcome"))("title") };
}

export default function WelcomePage() {
  return <Welcome />;
}
