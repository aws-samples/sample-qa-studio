# repeat

Runs the steps nested inside it once per row of a small table (columns + rows) — either inline on the step or an **application dataset** referenced by `dataset_id`. Every column is available to the nested steps as a `{{column}}` variable. Use it when the same actions must be exercised for several inputs — "log in as each of these users", "add each of these products to the cart" — instead of copying the steps N times.

Design-time only: the editor shows children nested under the repeat, but when an execution is created the repeat is unrolled into `rows × children` ordinary execution steps. The runner never sees a repeat.

## When to use

- **The same sequence of actions for several inputs.** Several users, several search terms, several products — one `repeat` with the inputs as rows.
- **Data-driven checks** where the expected value differs per input: put the expected value in a column and compare with an `assertion` child (`assertion_variable: "<column>"`).
- **Environment-specific datasets in CI.** The stored rows are the default; `qa-studio run --dataset-file` swaps in a CSV per environment without editing the test.
- **Rows shared by several tests of one application.** Reference an application dataset (`dataset_id`, managed with `qa-studio apps datasets …` or on the application's *Datasets* page) instead of inlining the same rows in every test; editing the dataset changes every test that references it. Prefer inline rows when only this test uses them.

## When NOT to use

- **A single input.** Just write the steps.
- **Different actions per input.** A repeat runs the *same* child steps for every row. If row 2 needs an extra click, write it as separate steps.
- **Looping over values discovered on the page.** Rows are static (authored or fed by CSV). There is no "for each item on the page".
- **Nested loops.** One nesting level only — a repeat cannot contain a repeat.
- **Templates.** Template steps reject `step_type: "repeat"` in v1.
- **Continue-on-failure.** The first failing expanded step fails the whole test (fail-fast); later rows stay `pending`.

## Inputs

| Field | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `step_type` | string | yes | — | `"repeat"`. |
| `instruction` | string | yes | — | Human label (e.g. `"Login as each user"`). Must be unique among the repeat steps of the test; `--dataset-file LABEL=…` targets it. |
| `dataset_id` | string | one of `dataset_id` / inline rows | — | Reference to an application dataset (`GET /applications/{id}/datasets`). The dataset must belong to the test's application; its columns and rows are resolved at execution time. Mutually exclusive with `repeat_columns` / `repeat_rows` (both → `repeat step cannot have both dataset_id and inline rows`; neither → `repeat step must have either dataset_id or repeat_columns/repeat_rows`). Not allowed in templates. |
| `repeat_columns` | list[string] | with `repeat_rows`, unless `dataset_id` | — | 1–20 identifiers (`^[A-Za-z_][A-Za-z0-9_]*$`), unique. Reserved names are rejected: `UniqueID`, `Time`, `ExecutionID`, `CreatedAt`, `RepeatIndex`, `RepeatTotal`. |
| `repeat_rows` | list[list[string]] | with `repeat_columns`, unless `dataset_id` | — | 1–100 rows; every row has exactly `len(repeat_columns)` string cells. Columns + rows serialized ≤ 200 KB. |
| `steps` | list[step] | yes (≥ 1 at run time) | `[]` | The child steps, in order. Any step type except `repeat`. In the API/DynamoDB shape children are flat records with `parent_step_id` = the repeat's `id`; the export/import JSON nests them here. |

Children get two extra variables per row: `{{RepeatIndex}}` (1-based row number) and `{{RepeatTotal}}` (row count).

Variable precedence inside a repeat: test `variables` < row columns < runtime captures (`retrieve_value` / `transform`) < built-ins.

Row-source precedence (lowest → highest): application dataset (`dataset_id`) → inline `repeat_columns` / `repeat_rows` (a step has one **or** the other) → `--dataset-file` for one run. The dataset is resolved when the execution is created (server) or, in `--local-only` mode, by the CLI through `GET /applications/{id}/datasets/{datasetId}` (needs `api/applications.read`). A missing dataset fails before anything runs: `400 {"error": "dataset not found", "dataset_id"}` remotely, exit 2 `dataset <id> not found in application <app>` locally.

## Output

No capture variable. At execution time the repeat produces no step of its own; each child becomes one execution step per row, in row-major order (row 1: child 1, child 2, …; row 2: child 1, …). Each expanded step carries `repeat_label`, `repeat_row_index`, `repeat_row_total` and `row_variables`, and the UI tags it `Row i/n`.

## Examples

Log in as each of two users and check the role shown in the header:

```json
{
  "sort": 2,
  "step_type": "repeat",
  "instruction": "Login as each user",
  "repeat_columns": ["email", "role"],
  "repeat_rows": [
    ["alice@example.com", "Administrator"],
    ["bob@example.com", "Viewer"]
  ],
  "steps": [
    {
      "sort": 3,
      "step_type": "browser",
      "instruction": "Open the login page",
      "browser_action": "navigate",
      "browser_args": "{\"url\": \"{{BASE_URL}}/login\"}"
    },
    {
      "sort": 4,
      "step_type": "navigation",
      "instruction": "Type {{email}} into the email field"
    },
    {
      "sort": 5,
      "step_type": "secret",
      "instruction": "Click into the password field.",
      "secret_key": "password"
    },
    {
      "sort": 6,
      "step_type": "navigation",
      "instruction": "Click the Sign in button"
    },
    {
      "sort": 7,
      "step_type": "validation",
      "instruction": "The header shows the role {{role}}",
      "validation_type": "bool",
      "validation_operator": "equals",
      "validation_value": "true"
    }
  ]
}
```

Compare a captured value against a dataset column with an `assertion` child:

```json
{
  "sort": 1,
  "step_type": "repeat",
  "instruction": "Check each product price",
  "repeat_columns": ["sku", "expected_price"],
  "repeat_rows": [["A-100", "19.99"], ["B-200", "4.50"]],
  "steps": [
    {
      "sort": 2,
      "step_type": "browser",
      "instruction": "Open the product page",
      "browser_action": "navigate",
      "browser_args": "{\"url\": \"{{BASE_URL}}/products/{{sku}}\"}"
    },
    {
      "sort": 3,
      "step_type": "retrieve_value",
      "instruction": "Get the displayed price",
      "capture_variable": "displayed_price",
      "value_type": "number"
    },
    {
      "sort": 4,
      "step_type": "assertion",
      "instruction": "Displayed price matches the catalogue",
      "assertion_variable": "displayed_price",
      "validation_type": "number",
      "validation_operator": "equals",
      "validation_value": "{{expected_price}}"
    }
  ]
}
```

Reference an application dataset instead of inlining the rows (the columns are the dataset's; find it with `qa-studio apps datasets list <app-id>`, create it with `qa-studio apps datasets create <app-id> customers --file customers.csv --output json`):

```json
{
  "sort": 1,
  "step_type": "repeat",
  "instruction": "Check each customer",
  "dataset_id": "0192b1c4-5d6e-7f80-9a1b-2c3d4e5f6a7b",
  "steps": [
    {
      "sort": 2,
      "step_type": "browser",
      "instruction": "Open the customer search",
      "browser_action": "navigate",
      "browser_args": "{\"url\": \"{{BASE_URL}}/customers\"}"
    },
    {
      "sort": 3,
      "step_type": "navigation",
      "instruction": "Type {{email}} into the search field"
    },
    {
      "sort": 4,
      "step_type": "validation",
      "instruction": "The first result shows {{first_name}} {{last_name}}",
      "validation_type": "bool",
      "validation_operator": "equals",
      "validation_value": "true"
    }
  ]
}
```

Export keeps `dataset_id` (rows are never inlined); import validates it against the target application (`--application-id`) and fails with `dataset not found in this application` otherwise. In the web UI this is the *Dataset source → Application dataset* choice on the repeat step; the step summary reads `Application dataset: customers · 5 rows · 3 columns`.

Feed the dataset from a CSV in CI (header row = the repeat's columns; works for inline rows and dataset references alike):

```bash
qa-studio run --usecase-id <id> --dataset-file "Login as each user=users-staging.csv"
```

## Common pitfalls

- **Forgetting to reset the page at the start of the loop body.** Browser state is *not* reset between rows: row 2 starts where row 1 left off (logged in, on the dashboard). Make the first child a `browser` → `navigate` to the entry page, and add a log-out click if the flow needs it.
- **Copying the steps N times instead of using a repeat.** Same actions for several inputs → one `repeat`. N copies drift apart and are tedious to maintain.
- **Duplicate labels.** Two repeats with the same `instruction` are rejected (400) — the label is how `--dataset-file` addresses the dataset.
- **Column names that collide with built-ins or variables.** `UniqueID` etc. are reserved. A column with the same name as a test variable shadows it inside the repeat; a runtime capture with the same name shadows the column.
- **Expecting the trajectory cache inside the loop.** Trajectory replay/save is off for expanded steps (the instruction differs per row after substitution). Expect every row to run through Nova Act.
- **Expecting later rows to run after a failure.** Fail-fast: the first failing step marks the execution failed and later rows stay `pending`. Fix the data or the flow and rerun.
- **Nesting a repeat in a repeat / `steps` on a non-repeat.** Both are rejected on import and in the editor.
- **`dataset_id` together with `repeat_columns` / `repeat_rows`, or neither.** Exactly one source: `repeat step cannot have both dataset_id and inline rows` / `repeat step must have either dataset_id or repeat_columns/repeat_rows`.
- **Copying a `dataset_id` into a test of another application or environment.** Dataset ids are scoped to one application (like template UUIDs to one environment): import returns `400 dataset not found in this application` with `datasetIds`; moving the test to another application is refused with `409 use case references application datasets`. Inline the rows or create the dataset in the target application and swap the id.
- **Deleting a dataset that tests still reference.** `409` listing the use cases; switch their repeat steps first.
- **`{{column}}` names that don't match the dataset's header.** With `dataset_id` the columns are not in the test JSON — check them with `qa-studio apps datasets get <app-id> <dataset-id>` before writing the children.
