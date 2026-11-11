# Repeat Step (data-driven loop over a dataset)

## Summary

A `repeat` step carries a small inline table (`repeat_columns` + `repeat_rows`) and contains child steps (`parent_step_id`). During execution the children run once per row, with every column exposed as a `{{column}}` variable. Nesting is design-time only: when an execution is created the repeat is unrolled into `rows × children` ordinary execution steps (`web-app/lambdas/endpoints/repeat_expansion.py`, mirrored for local-only runs in `qa-studio-cli/qa_studio_cli/runner/repeat_expansion.py`), so the runner never learns what a repeat is.

The full design — decisions, user journeys, data model, API changes, CLI `--dataset-file`, frontend behaviour, alternatives considered and operational impact — lives in the feature spec:

**→ [`.kiro/docs/repeat-step/design.md`](../../.kiro/docs/repeat-step/design.md)**

## Where to look

| Topic | Document |
|---|---|
| Authoring a repeat (agents) | [`skill/reference/step-types/repeat.md`](../../skill/reference/step-types/repeat.md) |
| Authoring a repeat (web UI) and reading `Row i/n` in executions | [`docs/user-guide.md`](../user-guide.md#repeat-steps-data-driven-loops) |
| Step fields, `repeat_datasets` execute body, expanded execution-step fields | [`docs/api-reference.md`](../api-reference.md#repeat-step-fields) |
| `qa-studio run --dataset-file` in CI | [`docs/ci-cd-integration.md`](../ci-cd-integration.md#using-dataset-overrides-repeat-steps) |
| Fail-fast rows / no trajectory replay inside a repeat | [`docs/troubleshooting.md`](../troubleshooting.md#repeat-step-issues) |
| Record types and expansion at execution-creation time | [`docs/architecture.md`](../architecture.md#data-storage) |
