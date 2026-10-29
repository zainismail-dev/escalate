/** The public live demo: bundled sample data, no API, nothing saved or sent (docs/DEPLOY_DEMO.md). */
export const DEMO_STATIC = process.env.NEXT_PUBLIC_DEMO_STATIC === "true";

export const REPO_URL = "https://github.com/zainismail-dev/escalate";

/** Fired when the demo refuses a write: the demo dialog opens. */
export const DEMO_WRITE_EVENT = "escalate:demo-write";
/** href for links that would download from the API (PDFs): opens the demo dialog instead. */
export const DEMO_LINK = "#demo-only";

/** What the wizard is pre-filled with in the demo (fictional). */
export const SAMPLE_CASE = {
  description:
    "I bought a pair of running shoes online for £89.99 on 3 March 2026 (order RS-20417). They split at the sole after two weeks. The shop refuses a refund and offers only store credit.",
  company: "StrideFast Sports",
  country: "GB",
  evidence: "sample-receipt.png",
};
