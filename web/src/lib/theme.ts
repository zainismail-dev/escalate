"use client";
import { useSyncExternalStore } from "react";
import { THEME_KEY } from "./theme-init";

/**
 * Light / dark / follow the system. The root layout runs THEME_INIT before the page paints
 * (next/script beforeInteractive), so there is no flash and no <script> inside a component.
 */
export type ThemeChoice = "system" | "light" | "dark";

const listeners = new Set<() => void>();

function read(): ThemeChoice {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

function apply(choice: ThemeChoice) {
  const dark = choice === "dark" || (choice === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  const mq = matchMedia("(prefers-color-scheme: dark)");
  const onSystem = () => {
    if (read() === "system") apply("system");
    cb();
  };
  mq.addEventListener("change", onSystem);
  window.addEventListener("storage", cb);
  return () => {
    listeners.delete(cb);
    mq.removeEventListener("change", onSystem);
    window.removeEventListener("storage", cb);
  };
}

export function setTheme(choice: ThemeChoice) {
  try {
    if (choice === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, choice);
  } catch {
    /* private mode: still apply for this page */
  }
  apply(choice);
  listeners.forEach((l) => l());
}

/** The saved choice. The server and the first client render both say "system" (no mismatch). */
export function useTheme(): ThemeChoice {
  return useSyncExternalStore(subscribe, read, () => "system");
}
