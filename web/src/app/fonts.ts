import {
  Bricolage_Grotesque,
  Instrument_Sans,
  JetBrains_Mono,
  Noto_Naskh_Arabic,
  Noto_Nastaliq_Urdu,
  Noto_Sans_Arabic,
  Noto_Sans_Devanagari,
  Noto_Serif_Devanagari,
  Source_Serif_4,
} from "next/font/google";

// Self-hosted at build time by next/font: no request to Google from the user's browser.
export const bricolage = Bricolage_Grotesque({ subsets: ["latin", "latin-ext"], weight: ["700", "800"], variable: "--font-bricolage" });
export const instrument = Instrument_Sans({ subsets: ["latin", "latin-ext"], variable: "--font-instrument" });
export const jetbrains = JetBrains_Mono({ subsets: ["latin", "latin-ext"], weight: ["400", "600", "700"], variable: "--font-jetbrains" });
export const sourceSerif = Source_Serif_4({ subsets: ["latin", "latin-ext"], variable: "--font-source-serif" });

// Script fallbacks (not preloaded: only fetched when such text is on the page).
export const notoArabic = Noto_Sans_Arabic({ subsets: ["arabic"], variable: "--font-noto-arabic", preload: false });
export const notoNaskh = Noto_Naskh_Arabic({ subsets: ["arabic"], variable: "--font-noto-naskh", preload: false });
export const notoNastaliq = Noto_Nastaliq_Urdu({ subsets: ["arabic"], variable: "--font-noto-nastaliq", preload: false });
export const notoDevanagari = Noto_Sans_Devanagari({ subsets: ["devanagari"], variable: "--font-noto-devanagari", preload: false });
export const notoSerifDevanagari = Noto_Serif_Devanagari({ subsets: ["devanagari"], variable: "--font-noto-serif-devanagari", preload: false });

export const fontVariables = [
  bricolage,
  instrument,
  jetbrains,
  sourceSerif,
  notoArabic,
  notoNaskh,
  notoNastaliq,
  notoDevanagari,
  notoSerifDevanagari,
]
  .map((f) => f.variable)
  .join(" ");
