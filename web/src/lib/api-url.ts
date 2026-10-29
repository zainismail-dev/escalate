/** Where the browser reaches the Escalate API (build-time). Not a secret: it is in the bundle.
 * Empty in the static demo, which has no API (and whose bundle must not name one). The env
 * check is inline so the build drops the other branch. */
export const API_URL =
  process.env.NEXT_PUBLIC_DEMO_STATIC === "true"
    ? ""
    : (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
