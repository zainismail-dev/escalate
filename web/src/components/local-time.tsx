"use client";
import { useSyncExternalStore } from "react";
import { formatDateTime, formatLocalDateTime } from "@/lib/format";

const subscribe = () => () => {};

/** A time in the viewer's zone, with UTC in the tooltip. The server doesn't know the zone, so
 * the first render (and hydration) is UTC and the local time follows after mount. */
export function LocalTime({ value, locale, className }: { value: string; locale: string; className?: string }) {
  const mounted = useSyncExternalStore(subscribe, () => true, () => false);
  const utc = formatDateTime(value, locale) ?? value;
  return (
    <time dateTime={value} title={utc} className={className}>
      {mounted ? formatLocalDateTime(value, locale) : utc}
    </time>
  );
}
