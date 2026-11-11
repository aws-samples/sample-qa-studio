# Templates — reuse steps across tests

A template is a named, reusable sequence of steps (plus optional variables) — "Login – Shop", "Dismiss cookie banner", "Open admin settings". Instead of re-typing the same login steps in every test JSON, reference the template once and let the cloud expand it at import time.

## Table of contents

- [When to use a template](#when-to-use-a-template)
- [Find and inspect templates](#find-and-inspect-templates)
- [Reference a template in a test JSON](#reference-a-template-in-a-test-json)
- [Create a template](#create-a-template)
- [Change a template (export → edit → update)](#change-a-template-export--edit--update)
- [Delete a template](#delete-a-template)
- [Insert a template into an existing test](#insert-a-template-into-an-existing-test)
- [Secrets and variables](#secrets-and-variables)
- [Rules and caveats](#rules-and-caveats)
- [Command reference](#command-reference)

---

## When to use a template

**Before hand-authoring login / setup / teardown steps, run `qa-studio templates list`.** If a fitting template exists, reference it by `template_id`. If the same sequence of steps appears (or will appear) in two or more tests and no template exists yet, create one and reference it from both.

Don't template a one-off sequence; a plain step list is simpler and the agent can still edit it inline.

## Find and inspect templates

```bash
# ID, step count, name, category — one line per template
qa-studio templates list
qa-studio templates list --format json

# Metadata, ordered steps, variables, required secret keys, and the tests using it ("Used by")
qa-studio templates get 3f1c0000-0000-4000-8000-000000000001
qa-studio templates get 3f1c0000-0000-4000-8000-000000000001 --format json
```

`templates get` prints `Required secrets: shop_username, shop_password` — these are the `secret_key`s of the template's `secret` steps and they will be prompted when a test referencing the template is imported. `Used by (N):` lists the tests that imported the template (`usages` in JSON).

## Reference a template in a test JSON

A placeholder step takes the template's slot. It has **exactly three fields** — anything else (an `instruction`, a `secret_key`, …) is rejected by `tests import`:

```json
{
  "exportVersion": "1.0",
  "exportedAt": "2025-01-01T00:00:00Z",
  "usecase": { "name": "Checkout", "starting_url": "https://shop.example.com", "tags": ["checkout"] },
  "steps": [
    { "sort": 1, "step_type": "template", "template_id": "3f1c0000-0000-4000-8000-000000000001" },
    { "sort": 2, "step_type": "navigation", "instruction": "Click 'Add to cart' on the first product." },
    { "sort": 3, "step_type": "validation", "instruction": "Return the cart badge count.",
      "validation_type": "number", "validation_operator": "exact", "validation_value": "1" }
  ],
  "variables": [],
  "secrets": []
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `sort` | int > 0 | yes | The slot where the template's steps are inserted |
| `step_type` | `"template"` | yes | Not an executable step type — it is replaced at import |
| `template_id` | UUID string | yes | From `qa-studio templates list` / `templates create` |

What happens on `qa-studio tests import`:

1. The CLI validates the file, fetches each referenced template once, and fails the file with `step 1: template <id> not found — run 'qa-studio templates list' or 'qa-studio templates create'` if a template does not exist. Nothing is written. `--dry-run` shows the referenced template names and the full list of required secrets (file secrets + template secrets).
2. The template's secret keys are prompted together with the file's own `secrets` — `--secret KEY=VALUE`, `--non-interactive` and `--skip-secrets` work the same for both. Do **not** list template secrets in the file's `secrets` array; the server derives them.
3. `POST /import` expands the placeholder server-side: the template's 4 steps become steps 1–4, the file's steps become 5–6, and the inserted steps keep their template linkage (`template_id`, `template_step_id`, `template_version`) so "update from template" hints appear in the web UI when the template changes later.

The same template may be referenced several times in one file (e.g. once per account). Placeholders are only allowed at the top level — not inside a `repeat` step's nested `steps`.

## Create a template

Write a template file. Steps use the same shape as test JSON steps; **one action or one check per step** applies here too.

```json
{
  "templateVersion": "1.0",
  "template": {
    "name": "Login – Shop",
    "description": "Signs in to the shop with the shop_* secrets.",
    "category": "auth",
    "tags": ["shop", "login"]
  },
  "steps": [
    { "sort": 1, "step_type": "browser", "instruction": "Open the login page.",
      "browser_action": "navigate", "browser_args": "{\"url\": \"https://shop.example.com/login\"}" },
    { "sort": 2, "step_type": "secret", "instruction": "Click into the email field.", "secret_key": "shop_username" },
    { "sort": 3, "step_type": "secret", "instruction": "Click into the password field.", "secret_key": "shop_password" },
    { "sort": 4, "step_type": "navigation", "instruction": "Click the 'Sign in' button." }
  ],
  "variables": [
    { "key": "shop_base_url", "value": "https://shop.example.com" }
  ]
}
```

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `templateVersion` | `"1.0"` | yes | — | File format version |
| `template.name` | string, min 1 | yes | — | Shown in `templates list` |
| `template.description` | string | no | `""` | |
| `template.category` | string | no | `""` | Free text, e.g. `auth` |
| `template.tags` | string[] | no | `[]` | |
| `steps` | step[], min 1 | yes | — | Same shape as test JSON steps; no `template` and no `repeat` steps |
| `steps[].id` | UUID string | no | — | Template step id. Emitted by `templates export`; `templates update` matches on it. Ignored by `templates create`. Duplicate → validation error |
| `variables` | `{key, value}[]` | no | `[]` | Merged into the test's variables at import (the test's own values win) |

There is no `secrets` block: required secrets are derived from the `secret_key` of `secret` steps.

```bash
# Validate only (prints name, step count, required secrets)
qa-studio templates create ./templates/login-shop.json --dry-run

# Create — prints the UUID to reference
qa-studio templates create ./templates/login-shop.json
# ✓ Template created: Login – Shop (ID: 3f1c0000-0000-4000-8000-000000000001)

qa-studio templates create ./templates/login-shop.json --format json
# {"id": "3f1c…", "name": "Login – Shop", "stepsCreated": 4}
```

Keep template files under version control next to the tests (`./templates/`), like test JSON.

## Change a template (export → edit → update)

**Never recreate a template to change it.** `templates create` always makes a *new* template with a *new* UUID; every placeholder and every `tests insert-template` that pointed at the old UUID keeps pointing there. Edit the existing template instead:

```bash
# 1. Export — every step carries its "id"
qa-studio templates export 3f1c… --output ./templates/login-shop.json

# 2. Edit the file: change an instruction, add a step (no "id"), remove a step, change the description …

# 3. Preview what will happen
qa-studio templates update 3f1c… ./templates/login-shop.json --dry-run
# Plan for "Login – Shop": 4 steps updated, 1 created, 0 deleted; metadata changed: description

# 4. Apply — one atomic PUT, one version bump
qa-studio templates update 3f1c… ./templates/login-shop.json
# ✓ Template updated: Login – Shop (version 7; 4 updated, 1 created, 0 deleted)
```

How steps are matched:

| Step in the file | Result |
|---|---|
| has `id` that exists in the template | updated in place — the step keeps its id, so tests that imported it still see it as *the same step* and get an "update available" hint |
| has no `id` | created (new id) |
| `id` not in the template | `steps[i]: id … does not belong to template …` — nothing written, exit 1 |
| existing step missing from the file | deleted |

`sort` is renumbered `1..n` from the file order. **Keep the `id`s in exported files** — stripping them turns every update into "delete all + create all", which breaks the link to every test that imported the template. Metadata (`name`, `description`, `category`, `tags`) and `variables` are replaced with the file's values.

`templates export` without `--output` prints the file to stdout (`> file` works). Fields are emitted in a stable order (`id`, `sort`, `step_type`, `instruction`, then alphabetically) so diffs under version control stay readable.

## Delete a template

```bash
qa-studio templates delete 3f1c…
# Template "Login – Shop" is used by 2 tests (steps are kept, template link removed). Delete? [y/N]: y
# ✓ Template 3f1c… deleted.

# Scripts / CI: skip the prompt
qa-studio templates delete 3f1c… --yes
```

What happens to tests that imported the template: **their steps are kept exactly as they are**; only the template linkage is removed, so they become plain steps (no "From template" link, no "update available" hints). Nothing stops running. `templates get <id>` shows the same information beforehand under `Used by (N):`. An unknown id exits 1 before any prompt; answering `n` prints `Aborted.` and exits 0.

## Insert a template into an existing test

For a test that already lives in the cloud (no local JSON, or you don't want to re-import):

```bash
# Append at the end
qa-studio tests insert-template <usecase-id> --template-id 3f1c…

# The template's first step becomes step 2; old steps 2..n shift down
qa-studio tests insert-template <usecase-id> --template-id 3f1c… --position 2

# Set the template's secrets right away (dev credentials only — see the transcript caveat in SKILL.md)
qa-studio tests insert-template <usecase-id> --template-id 3f1c… --position 2 \
  --secret shop_username=qa@dev.local --secret shop_password=devpass123

qa-studio tests insert-template <usecase-id> --template-id 3f1c… --format json
# {"usecaseId": "...", "templateId": "3f1c…", "position": null, "stepsCreated": 4,
#  "secretsSet": [], "missingSecrets": ["shop_username", "shop_password"]}
```

Steps are renumbered `1..n` contiguously after the insert. Unsupplied secrets are listed as `⚠ Missing secrets (set in UI or pass --secret): …`; there is no interactive prompt on this command. A `--secret` key the template does not use exits with code 2 before anything is inserted.

## Secrets and variables

- **Secrets** are never stored in templates or template files. The template's `secret` steps name a `secret_key`; the *value* is set per test — at `tests import` (prompt / `--secret`), via `tests insert-template --secret`, or in the web UI. All fields of a login form are secrets (username, email, password, OTP), not just the password.
- **Variables** declared in the template are merged into the test's variables at import. If the test already defines the same key, the test's value wins.

## Rules and caveats

- **UUIDs are per environment.** A template created in dev has a different `template_id` than the same template in prod. A test JSON referencing a dev UUID fails in prod with `template … not found` — recreate the template there (`templates create`) and update the `template_id`.
- **No nesting.** A template cannot contain a `template` step (`templates cannot contain template steps`), nor a `repeat` step.
- **Placeholders carry exactly `sort`, `step_type`, `template_id`.** Extra fields fail local validation.
- **Expansion is server-side.** The CLI never rewrites your JSON; the cloud test contains the expanded steps with template linkage.
- **Editing a template** later does not change tests that already imported it — they show an "update available" hint in the web UI and can be updated step by step.
- **Never recreate a template to change it.** The UUID changes and every placeholder / inserted reference breaks. Use `templates export` → edit → `templates update`.
- **Keep `id`s in exported files.** They are how `templates update` knows which step is which; without them every step is deleted and recreated.
- **Deleting a template keeps the tests intact.** Their steps stay; only the template link is removed. Check `templates get <id>` (`Used by`) or let `templates delete` show the count before confirming.

## Command reference

| Command | Options | Default | Exit codes |
|---|---|---|---|
| `qa-studio templates list` | `--format human\|json` | `human` | `0`; `1` API error |
| `qa-studio templates get <id>` | `--format human\|json` | `human` | `0`; `1` API error / not found |
| `qa-studio templates create <path>` | `--dry-run`, `--format human\|json` | off, `human` | `0`; `1` invalid file or API error; `2` file missing |
| `qa-studio templates export <id>` | `--output PATH` | stdout | `0`; `1` API error / not found / unwritable path |
| `qa-studio templates update <id> <path>` | `--dry-run`, `--format human\|json` | off, `human` | `0`; `1` invalid file, unknown step id, or API error; `2` file missing |
| `qa-studio templates delete <id>` | `--yes` / `-y` | prompt | `0` (also when aborted); `1` API error / not found |
| `qa-studio tests insert-template <usecase-id>` | `--template-id UUID` (required), `--position N` (≥ 1, default append), `--secret KEY=VALUE` (repeatable), `--format human\|json` | append, `human` | `0`; `1` API error or secret write failed; `2` usage error (bad position, unknown secret key) |
