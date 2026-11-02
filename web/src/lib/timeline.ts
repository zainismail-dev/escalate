import type { TimelineEvent } from "./types";

export type TimelineEntry = TimelineEvent & { retries: number };

const STARTED = "case_started";

/** The agent logs "started" on every attempt: show one entry, at the first start, with a count.
 * Everything else that happened between the attempts keeps its place. */
export function collapseRetries(events: TimelineEvent[]): TimelineEntry[] {
  const retries = Math.max(events.filter((e) => e.type === STARTED).length - 1, 0);
  const first = events.find((e) => e.type === STARTED);
  return events.filter((e) => e.type !== STARTED || e === first).map((e) => ({ ...e, retries: e === first ? retries : 0 }));
}
