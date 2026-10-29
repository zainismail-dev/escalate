/** Where the browser reaches the Escalate API (build-time). Not a secret: it is in the bundle. */
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
