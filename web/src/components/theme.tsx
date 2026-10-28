"use client";
import { Monitor, Moon, Sun } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { setTheme, useTheme } from "@/lib/theme";

const ORDER = ["system", "light", "dark"] as const;

/** Cycles system -> light -> dark. The label says what it is now and what a click does. */
export function ThemeToggle() {
  const t = useTranslations("theme");
  const current = useTheme();
  const next = ORDER[(ORDER.indexOf(current) + 1) % ORDER.length];
  const Icon = current === "dark" ? Moon : current === "light" ? Sun : Monitor;
  const label = t("toggle", { current: t(current), next: t(next) });
  return (
    <Button variant="ghost" size="icon" onClick={() => setTheme(next)} aria-label={label} title={label} data-testid="theme-toggle">
      <Icon aria-hidden />
    </Button>
  );
}
