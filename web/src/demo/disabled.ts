/** Stands in for ./backend.ts in every build except the static demo (next.config.ts alias), so
 * self-hosted bundles carry no sample data. Never called: request() only uses it in the demo. */
export class DemoBlocked extends Error {}
export const SAMPLE_REPLY = "";
export async function demoRequest<T>(): Promise<T> {
  throw new Error("not the static demo build");
}
