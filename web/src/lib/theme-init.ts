/**
 * Runs before the page paints (root layout, next/script beforeInteractive): applies the saved
 * theme, or the system one, so there is no flash. A plain module, not "use client", so the
 * server layout gets the string itself. Kept tiny and dependency-free: it runs before React.
 */
export const THEME_KEY = "escalate-theme";

export const THEME_INIT = `(function(){try{var c=localStorage.getItem("${THEME_KEY}");var d=c==="dark"||(c!=="light"&&matchMedia("(prefers-color-scheme: dark)").matches);var e=document.documentElement;e.classList.toggle("dark",d);e.style.colorScheme=d?"dark":"light"}catch(_){}})();`;
