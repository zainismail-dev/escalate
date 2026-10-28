import { cn } from "@/lib/utils";

/** Rounded square with three ascending bars: the escalation ladder. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-8 shrink-0", className)} aria-hidden focusable="false">
      <rect width="32" height="32" rx="8" fill="#14161F" />
      <rect x="0.5" y="0.5" width="31" height="31" rx="7.5" fill="none" stroke="#262A36" />
      <rect x="7" y="18" width="4.5" height="7" rx="1.5" fill="#D7F36B" opacity="0.55" />
      <rect x="13.75" y="13" width="4.5" height="12" rx="1.5" fill="#D7F36B" opacity="0.8" />
      <rect x="20.5" y="7" width="4.5" height="18" rx="1.5" fill="#D7F36B" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <LogoMark />
      <span className="font-display text-xl font-extrabold tracking-[-0.03em]">Escalate</span>
    </span>
  );
}
