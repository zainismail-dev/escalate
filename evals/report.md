# Eval report

- Run: 2026-10-28 11:36 UTC
- Model: oracle (expected answers)
- Golden set: 50 cases, 40 sample replies
- **Oracle run:** checks the harness only; not a quality score.

| Eval | Result | Target | Pass |
| --- | --- | --- | --- |
| Fact extraction field accuracy | 100.0% (352/352) | ≥ 95% | ✅ |
| Case type + country + region | 100.0% (50/50); type only 100.0% | ≥ 95% | ✅ |
| Unsupported facts in drafts | 0 in 50 drafts | 0 | ✅ |
| Drafts flagged for threats or rudeness | 0 flags in 50 drafts | 0 | ✅ |
| Reply verdict correct | 100.0% (40/40) | ≥ 90% | ✅ |

## History

Before/after numbers for each quality change. Real-model rows are filled in by running
`uv run python -m evals.run --suite all` with a local model (see docs/MANUAL_STEPS.md).

| Date | Change | Model | Extraction | Classification | Unsupported | Tone | Replies |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-28 | Baseline (task 3.6) | oracle | 100% | 100% | 0 | 0 | 100% |
| 2026-10-28 | Task 4.1: code tone gate in fact check; few-shot reply-judge examples (incl. auto-acknowledgement → no_reply); classify gives case-type definitions and city → region hints; extraction keeps names/IDs verbatim and maps currency words to ISO codes | oracle | 100% | 100% | 0 | 0 | 100% |
| pending | Same prompts, first real-model run | _your local model_ | — | — | — | — | — |
