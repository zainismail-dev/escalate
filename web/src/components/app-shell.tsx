"use client";
import { Briefcase, Home, Plus, Settings as Cog } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useLocale, useMessages, useTranslations } from "next-intl";
import { useTransition } from "react";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme";
import { NativeSelect } from "@/components/ui/input";
import { ENABLED_LOCALES, LOCALE_COOKIE } from "@/i18n/config";
import { languageName } from "@/lib/format";
import { cn } from "@/lib/utils";

export function UiLanguageSelect({ className, id = "ui-language" }: { className?: string; id?: string }) {
  const locale = useLocale();
  const t = useTranslations("lang");
  const router = useRouter();
  const [pending, start] = useTransition();
  return (
    <>
      <label htmlFor={id} className="sr-only">
        {t("label")}
      </label>
      <NativeSelect
        id={id}
        value={locale}
        disabled={pending}
        className={cn("h-9 w-auto text-xs", className)}
        onChange={(e) => {
          document.cookie = `${LOCALE_COOKIE}=${e.target.value}; path=/; max-age=31536000; samesite=lax`;
          start(() => router.refresh());
        }}
      >
        {ENABLED_LOCALES.map((l) => (
          <option key={l} value={l}>
            {languageName(l, l)}
          </option>
        ))}
      </NativeSelect>
    </>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const t = useTranslations("nav");
  const tl = useTranslations("lang");
  const path = usePathname();
  const messages = useMessages() as { meta?: { translated?: boolean } };
  const landing = path === "/";
  const tabs = [
    { href: "/cases", label: t("cases"), icon: Briefcase, active: path === "/cases" || /^\/cases\/\d/.test(path) },
    { href: "/cases/new", label: t("newCase"), icon: Plus, active: path.startsWith("/cases/new") },
    { href: "/settings", label: t("settings"), icon: Cog, active: path.startsWith("/settings") },
  ];
  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:start-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-lime focus:px-3 focus:py-2 focus:text-on-lime">
        {t("skip")}
      </a>
      <header
        className={cn(
          "sticky top-0 z-40 border-b backdrop-blur",
          landing ? "dark border-night-line bg-night/90 text-text" : "border-line bg-bg/85",
        )}
      >
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4">
          <Link href="/" className="rounded-lg" aria-label={t("home")}>
            <Logo />
          </Link>
          <nav aria-label={t("main")} className="ms-6 hidden gap-1 md:flex">
            {tabs.map((tab) => (
              <Link
                key={tab.href}
                href={tab.href}
                aria-current={tab.active ? "page" : undefined}
                className={cn(
                  "rounded-lg px-3 py-2 text-sm font-semibold text-text-2 hover:bg-raised hover:text-text",
                  tab.active && "bg-raised text-text",
                )}
              >
                {tab.label}
              </Link>
            ))}
          </nav>
          <div className="ms-auto flex items-center gap-1">
            {ENABLED_LOCALES.length > 1 && <UiLanguageSelect />}
            <ThemeToggle />
          </div>
        </div>
      </header>
      {messages.meta?.translated === false && (
        <div className="border-b border-line bg-info-bg px-4 py-2 text-center text-xs text-info" data-testid="translate-banner">
          {tl("notTranslated")}{" "}
          <a className="font-semibold underline" href="https://github.com/zainismail-dev/escalate/blob/main/CONTRIBUTING.md" target="_blank" rel="noreferrer noopener">
            {tl("helpTranslate")}
          </a>
        </div>
      )}
      <main id="main" className={cn("flex-1", !landing && "mx-auto w-full max-w-6xl px-4 pb-28 pt-6 md:pb-12")}>
        {children}
      </main>
      <nav aria-label={t("main")} className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-card/95 backdrop-blur md:hidden" data-testid="bottom-tabs">
        <ul className="mx-auto grid max-w-md grid-cols-4">
          <li>
            <Link href="/" aria-current={landing ? "page" : undefined} className={cn("flex flex-col items-center gap-0.5 py-2.5 text-[0.6875rem] font-semibold text-muted", landing && "text-text")}>
              <Home className="size-5" aria-hidden />
              {t("home")}
            </Link>
          </li>
          {tabs.map((tab) => (
            <li key={tab.href}>
              <Link
                href={tab.href}
                aria-current={tab.active ? "page" : undefined}
                className={cn("flex flex-col items-center gap-0.5 py-2.5 text-[0.6875rem] font-semibold text-muted", tab.active && "text-text")}
              >
                <span className={cn("grid h-6 w-10 place-items-center rounded-full", tab.active && "bg-lime text-on-lime")}>
                  <tab.icon className="size-5" aria-hidden />
                </span>
                {tab.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
