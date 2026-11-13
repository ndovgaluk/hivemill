# reviewer plugins

Factory-authored, text only. `reviewer-skills` holds the `multi-angle-review` skill; the Workflow script it runs lives in `roles/workflows/` (scripts are banned inside plugins). See `docs/review-workflow.md`.

- `go-review`: the G1-G12 checklist for diffs that touch Go (docs/adr/0001-language-policy.md).
- `rework-brief`: the format of a FAIL verdict summary, the coder's whole rework request (rule R8 in roles/reviewer.md).

Role rule (G-041 SC4): a new .py file in a PR is a blocking finding; see roles/reviewer.md.
