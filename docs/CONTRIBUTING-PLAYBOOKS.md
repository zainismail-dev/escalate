# Contributing a playbook

A playbook is the escalation ladder for one case type in one place: who to write to first, how
long to wait, and where to go next, up to the consumer court. People will rely on these files
to send letters about their own money, so **every rule must come from an official source**.

## What a pack contains

```
playbooks/<cc>/<sector>/<case_type>[.<company>].yaml   # the ladder
playbooks/<cc>/scam_checklist.yaml                     # urgent steps for scam cases
templates/<cc>/<lang>/*.md.j2                          # the letters (en/ is required)
```

- `<cc>` is the lower-case ISO 3166-1 code (`pk`, `in`, `gb`, `us`). Inside the YAML, `country`
  is upper case (`PK`), and `regions` are ISO 3166-2 codes (`PK-SD`, `US-CA`).
- `<case_type>` is `refund_refused`, `subscription_cancel` or `scam`.
- The resolver picks the most specific file: company → region → country → `intl/generic`.
  To cover one state or province, add a file with `regions: [US-CA]`.

Start by copying `playbooks/pk/ecommerce/refund_refused.yaml` (the fullest example) and the
templates it uses. `schema/playbook.schema.json` lists every field.

## Rules

1. **Cite official sources.** Each playbook needs at least one entry under `sources`, with a
   `url` from a government, regulator, court or recognised consumer body. A source without a URL
   triggers a validator warning and will not be merged.
2. **Never guess.** If you are not sure of an authority's name, a phone number, a URL, a time
   limit or a section number, leave a `TODO(verify)` comment instead. A missing fact is safe; a
   wrong one can make someone miss a deadline.
3. **Facts only in templates.** Templates may only use the playbook's `required_facts` and
   `optional_facts`, plus `today`, `reply_by`, `language`, `locale`, `generic`, `case_ref` and
   `late`. The validator fails on anything else. Don't hard-code amounts, dates or IDs.
4. **Optional facts must be guarded:** `{% if return_tracking %} … {% endif %}`.
5. **Never ask for secrets.** No fact may be a password, PIN, OTP or card security code; the
   validator rejects such names. Card numbers: `card_last4` only.
6. **Tone:** firm, polite, factual. No threats, insults or legal claims your sources don't
   support.
7. **English first.** Every template needs an `en/` version; add other languages beside it
   (`templates/pk/ur/`). Ask a native speaker to review translations.
8. **Scam checklists** must keep the two warnings (we never ask for passwords/PINs/OTPs; beware
   of "recovery" scammers); the validator checks for them.

## Deadlines

```yaml
deadlines:
  - id: court_filing_limit
    rule: "30 days from cause of action; court may condone delay with reasons"
    days: 30
    from_fact: cause_of_action_on   # if the user knows the date
    from_step: s3_legal_notice      # otherwise: when this step's wait runs out
    warn_when_days_left: 10
```

Only add `days` when an official source states the limit. If a late filing can be excused, put
the application template in the court step's `adds_if_late`.

## Check your work

```bash
uv run python -m escalate.playbooks.validate playbooks/
uv run pytest -q
```

The validator must pass with no errors. Then:

- set `last_verified` to the date you checked the sources (the validator warns after 12 months);
- bump `version` and add a line to the changelog comment at the top of the file;
- remove each `TODO(verify)` you resolved, citing the source in `sources`.

## Submitting

1. Open an issue with the **New playbook** template first, so others know you're working on it.
2. Open a pull request labelled `playbook` and `country:<cc>`. In the description, list each rule
   and the source you took it from.
3. A maintainer checks the sources before merging. Packs reviewed by a lawyer or a
   consumer-rights group say so in their changelog.

Found a mistake in an existing pack? Use the **Playbook correction** issue template and cite
the official source that shows the correct rule.
