/**
 * Dates and times are formatted in UTC with an explicit locale, so the server render and the
 * browser produce the same string (no hydration mismatch). Times show their zone ("UTC").
 */
const TIME_ZONE = "UTC";

function toDate(value: string | Date): Date {
  if (value instanceof Date) return value;
  if (value.length === 10) return new Date(`${value}T12:00:00Z`); // a calendar date
  return new Date(value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
}

export function formatDate(value: string | Date | null | undefined, locale: string, style: "medium" | "long" = "medium") {
  if (!value) return null;
  const d = toDate(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return new Intl.DateTimeFormat(locale, { dateStyle: style, timeZone: TIME_ZONE }).format(d);
}

export function formatDateTime(value: string | null | undefined, locale: string) {
  if (!value) return null;
  const d = toDate(value);
  if (Number.isNaN(d.getTime())) return value;
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: TIME_ZONE,
    timeZoneName: "short",
  }).format(d);
}

/** The viewer's own time zone (`timeZone` is for tests). Only call this after mount: the server
 * doesn't know the zone. See `LocalTime`. */
export function formatLocalDateTime(value: string | null | undefined, locale: string, timeZone?: string) {
  if (!value) return null;
  const d = toDate(value);
  if (Number.isNaN(d.getTime())) return value;
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone,
    timeZoneName: "short",
  }).format(d);
}
