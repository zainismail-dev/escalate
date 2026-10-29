import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import noUnsanitized from "eslint-plugin-no-unsanitized";
import security from "eslint-plugin-security";

const config = [
  ...nextVitals,
  ...nextTs,
  // Security: no raw HTML sinks (innerHTML, insertAdjacentHTML, document.write), no eval-like
  // calls, and Node's risky patterns. User and AI text is only ever rendered as React text.
  security.configs.recommended,
  noUnsanitized.configs.recommended,
  {
    rules: {
      "react/no-danger": "error",
      "no-eval": "error",
      "no-implied-eval": "error",
      "no-new-func": "error",
      "no-script-url": "error",
      "react/jsx-no-script-url": "error",
      "react/jsx-no-target-blank": ["error", { allowReferrer: false }],
      // Flags every obj[key] read. It targets prototype pollution through writes keyed by user
      // input; here keys are TypeScript unions or API enums, and nothing assigns by user key.
      "security/detect-object-injection": "off",
    },
  },
  {
    // Build scripts and tests read repo files by computed path at build time, not user input.
    files: ["scripts/**", "tests/**", "e2e/**", "playwright.config.ts"],
    rules: {
      "security/detect-non-literal-fs-filename": "off",
      "security/detect-non-literal-regexp": "off",
    },
  },
  { ignores: [".next/**", "node_modules/**", "playwright-report/**", "test-results/**", "next-env.d.ts"] },
];

export default config;
