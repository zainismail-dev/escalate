// node --test tests/ : the web formatter must match the API's for every shared case.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { formatMoney } from "../src/lib/money.ts";

const fixtures = JSON.parse(readFileSync(new URL("../../schema/money_format_cases.json", import.meta.url), "utf8")) as {
  cases: { amount: string; currency: string; locale: string; expected: string; web?: boolean }[];
};

for (const c of fixtures.cases.filter((x) => x.web !== false)) {
  test(`${c.amount} ${c.currency} in ${c.locale}`, () => {
    assert.equal(formatMoney(c.amount, c.currency, c.locale), c.expected);
  });
}

test("empty and non-numeric amounts", () => {
  assert.equal(formatMoney(null, "USD", "en-US"), null);
  assert.equal(formatMoney("about forty", "USD", "en-US"), "about forty");
});
