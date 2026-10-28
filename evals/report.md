# Eval report

- Run: 2026-10-28 11:33 UTC
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
