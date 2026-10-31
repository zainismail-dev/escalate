import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { SignIn } from "./view";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("hosted.signin"))("title") };
}

export default function SignInPage() {
  return <SignIn />;
}
