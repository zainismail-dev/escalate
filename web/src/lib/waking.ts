/** The hosted API sleeps when idle (free plan) and takes up to a minute to wake. Requests that
 * fail with a network error or a proxy error page (502/503/504 without our JSON) are retried
 * with backoff for about 90 seconds, and the app shows "Waking the server…" meanwhile. */
export const WAKE_DELAYS_MS = [1500, 2500, 4000, 6000, 8000, 10000, 12000, 15000, 15000, 15000];

export function isWakingResponse(status: number, contentType: string | null): boolean {
  return [502, 503, 504].includes(status) && !(contentType ?? "").includes("application/json");
}

export async function withWakeRetries(
  attempt: () => Promise<Response>,
  onWaking: (waking: boolean) => void,
  sleep: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms)),
): Promise<Response> {
  let waking = false;
  try {
    for (let i = 0; ; i++) {
      let res: Response | null = null;
      let failure: unknown = null;
      try {
        res = await attempt();
      } catch (e) {
        failure = e;
      }
      const retry = failure !== null || (res !== null && isWakingResponse(res.status, res.headers.get("content-type")));
      if (!retry && res) return res;
      if (i >= WAKE_DELAYS_MS.length) {
        if (res) return res;
        throw failure;
      }
      if (!waking) onWaking((waking = true));
      await sleep(WAKE_DELAYS_MS[i]);
    }
  } finally {
    if (waking) onWaking(false);
  }
}
