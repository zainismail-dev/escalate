import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Waitlist } from "./view";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("hosted.waitlist"))("title") };
}

export default function WaitlistPage() {
  return <Waitlist />;
}
