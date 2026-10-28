# Good first issues

Ten issues ready to open on GitHub. Suggested labels are in brackets.

1. **Verify the Pakistan legal notice and court templates with a lawyer** —
   `templates/pk/en/*` and `templates/pk/ur/*`; record the review in the playbook changelog.
   [`playbook`, `country:pk`, `help wanted`]
2. **Name each Pakistani province's Consumer Protection Act** — resolve the `TODO(verify)` block in
   `playbooks/pk/ecommerce/refund_refused.yaml` with official sources. [`playbook`, `country:pk`, `good first issue`]
3. **Add a Khyber Pakhtunkhwa (PK-KP) region check** — confirm whether the PK ladder and the 30-day
   limit apply as written, or add a `regions: [PK-KP]` file. [`playbook`, `country:pk`, `good first issue`]
4. **Complete the Urdu UI translation** — fill the missing keys in `locales/ur.json` (compare with
   `locales/en.json`). [`i18n`, `good first issue`]
5. **Verify India's consumer complaint time limit** — confirm the two-year limit in
   `playbooks/in/general/refund_refused.yaml`, add the official source and section, remove the TODO.
   [`playbook`, `country:in`, `good first issue`]
6. **Add official URLs to the India, UK and US scam checklists** — replace each `TODO(verify)` in
   `playbooks/{in,gb,us}/scam_checklist.yaml` with links from government sites. [`playbook`, `good first issue`]
7. **Split the UK pack by nation** — region playbooks for Scotland (GB-SCT) and Northern Ireland
   (GB-NIR), whose small-claims routes differ. [`playbook`, `country:gb`]
8. **Add a Hindi translation of the India templates** — `templates/in/hi/`. [`i18n`, `country:in`, `good first issue`]
9. **Add a playbook for a new country** — e.g. Nigeria, Kenya or Brazil (`refund_refused` first),
   following `docs/CONTRIBUTING-PLAYBOOKS.md`. [`playbook`, `good first issue`]
10. **Add more golden eval cases in your language** — extend `evals/make_golden.py` with realistic
    synthetic complaints and expected facts. [`evals`, `good first issue`]
