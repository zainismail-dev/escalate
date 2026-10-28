"use client";
import { useEffect, useState } from "react";
import { api } from "./api";

let cached: Promise<string[]> | null = null;

/**
 * Letter languages the API allows (ENABLED_LETTER_LANGUAGES; v0.1: ["en"]). Language pickers,
 * side-by-side views and the language on case chips only show when there is more than one.
 */
export function useLetterLanguages(): string[] {
  const [langs, setLangs] = useState<string[]>(["en"]);
  useEffect(() => {
    cached ??= api
      .settings()
      .then((s) => s.enabled_letter_languages)
      .catch(() => ["en"]);
    let live = true;
    void cached.then((v) => live && setLangs(v));
    return () => {
      live = false;
    };
  }, []);
  return langs;
}
