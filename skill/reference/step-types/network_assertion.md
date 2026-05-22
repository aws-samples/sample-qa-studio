# network_assertion

Couples a UI action with an HTTP observation. When the step's instruction triggers an outbound request matching the configured URL pattern, QA Studio can verify the request shape, mock the response, and/or assert on the response status and body. The step is the bridge between UI testing and API contract testing.

## When to use

- **Verify a UI action triggers the expected API call** — URL, method, request body shape.
- **Drive the UI into specific states** by mocking the response (loading, error, empty list, large list).
- **Test against edge-case backend payloads** without touching the real backend.
- **Assert response structure with a JSON Schema** — great for list endpoints where "every item has these fields" matters but the array length doesn't.
- **Pin a response status** explicitly (e.g., `201` after a create).

## When NOT to use

- **You only care about the rendered UI** after the call. Use [`validation`](./validation.md) on the post-response page state. `network_assertion` adds overhead (interception, body parsing) that's wasted if the rendered result alone is what matters.
- **The action triggers a file download.** Use [`download`](./download.md). Browsers handle download responses outside the normal request/response interception path.
- **Non-JSON response bodies** (HTML, binary). The body assertion modes (`subset`, `schema`) are JSON-only. Use [`validation`](./validation.md) on the rendered result instead.
- **You want to inspect the response in a later step.** `network_assertion` doesn't capture the body into a variable. If you need that, capture from the rendered DOM with [`retrieve_value`](./retrieve_value.md).

## Inputs

| Field | Type | Required | Purpose |
|---|---|---|---|
| `step_type` | string | yes | `"network_assertion"`. |
| `instruction` | string | yes | Natural-language description of the UI action that triggers the request (e.g. `"Click Submit"`). |
| `network_url_pattern` | string | yes | Playwright glob pattern (e.g. `**/api/users`). |
| `network_method` | string | no | Expected HTTP verb. Empty = no method check. |
| `network_request_body` | string (JSON) | no | Expected request body. Interpreted per `network_body_match_type`. |
| `network_body_match_type` | string | no | `"exact"` (default), `"subset"`, or `"schema"`. |
| `network_mock_response` | string (JSON) | no | `{"status": …, "body": …, "headers": …}`. |
| `network_mock_passthrough` | boolean | no | If `true`, fetch the real response and merge overrides on top. |
| `network_timeout` | int | no | Wait timeout in seconds, range `[1, 120]`. Default `15`. |
| `network_response_body` | string (JSON) | no | Expected response body. Interpreted per `network_response_body_match_type`. |
| `network_response_body_match_type` | string | no | `"subset"` (default) or `"schema"`. **`"exact"` is rejected on the response side.** |
| `network_response_status` | int | no | Exact-match expected HTTP status, range `[100, 599]`. |

### Match types

- **`exact`** — captured body parsed as JSON must equal the expected body exactly. Extra keys fail. Request-side only.
- **`subset`** — every key/value in the expected template must be present in the captured body. Extra keys are ignored. Arrays match element-by-element with strict length equality.
- **`schema`** — the expected body is a [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) document. The captured body is validated against it. External `$ref` (`http://`, `https://`, `file://`) is rejected; only local-pointer refs (`#/...`) are allowed. Schema mode is the right choice when you care about structure, not specific values.

### Operating modes

1. **Assert-only** — configure URL (and any of method/body/response-status/response-body). The request goes through to the real server; every configured field is verified.
2. **Mock-only** — configure URL + `network_mock_response`. The real server is never called.
3. **Mock + assert** — both: return a mock AND verify the request and/or the (mocked) response.

## Output

No capture variable. The step succeeds if every configured assertion passes. Captured request/response bodies are summarized in the step logs (truncated to 500 chars; full bodies are not stored).

## Examples

Verify a click triggers a POST with a specific body:

```json
{
  "step_type": "network_assertion",
  "instruction": "Click Save",
  "network_url_pattern": "**/api/users",
  "network_method": "POST",
  "network_request_body": "{\"name\": \"John\"}",
  "network_body_match_type": "subset",
  "network_timeout": 15
}
```

Drive the UI into an error state by mocking a 503:

```json
{
  "step_type": "network_assertion",
  "instruction": "Click Refresh",
  "network_url_pattern": "**/api/users",
  "network_method": "GET",
  "network_mock_response": "{\"status\": 503, \"body\": {\"error\": \"unavailable\"}}"
}
```

Schema-validate a list endpoint without coupling to length:

```json
{
  "step_type": "network_assertion",
  "instruction": "Click Refresh",
  "network_url_pattern": "**/api/suites",
  "network_method": "GET",
  "network_response_status": 200,
  "network_response_body_match_type": "schema",
  "network_response_body": "{\"type\":\"object\",\"required\":[\"suites\"],\"properties\":{\"suites\":{\"type\":\"array\",\"items\":{\"type\":\"object\",\"required\":[\"id\",\"name\"],\"properties\":{\"id\":{\"type\":\"string\"},\"name\":{\"type\":\"string\"}}}}}}"
}
```

Assert request AND response in one step:

```json
{
  "step_type": "network_assertion",
  "instruction": "Click Save",
  "network_url_pattern": "**/api/users",
  "network_method": "POST",
  "network_request_body": "{\"name\": \"John\"}",
  "network_body_match_type": "subset",
  "network_response_status": 201,
  "network_response_body_match_type": "schema",
  "network_response_body": "{\"type\":\"object\",\"required\":[\"id\",\"name\"],\"properties\":{\"id\":{\"type\":\"string\"},\"name\":{\"type\":\"string\",\"const\":\"John\"}}}"
}
```

Notice `"const": "John"` inside the schema — pins a specific value while keeping schema-style structural checks for the rest.

## Security and resource limits

- **1 MiB cap** on each of: request body, response body, mock response, schema document. Configurable per deployment via `networkAssertionBodyMaxBytes` in `configuration.json`.
- **Subset matcher refuses** nested JSON deeper than 20 levels.
- **Schema mode rejects** external `$ref` URIs to prevent SSRF and file-read attacks.
- **Captured body sizes** are always checked even when no body assertion is configured — an oversized response fails the step early.
- **Captured bodies in logs** are truncated to 500 chars; only a match summary is persisted.
- **Route handlers are cleaned up** after the step (no interception leaks into later steps).

## `exact` rejected on response side

`network_response_body_match_type` accepts only `subset` or `schema`. **`exact` is deliberately rejected** because response payloads commonly contain non-deterministic values (server timestamps, generated IDs, ordering). Express tight comparisons via a schema with `const` values, or via a `subset` template over the stable keys.

## Caching

`network_assertion` is **not cached**. An API contract change must never be hidden by a cache hit.

## Common pitfalls

- **Wrong URL pattern.** `**/api/users` matches any host with a `/api/users` path; `https://exact-host.com/api/users` matches only that host. Glob patterns are Playwright-style; test the pattern against the expected URL before relying on it.
- **`subset` vs `schema` confusion.** `subset` requires array length equality; `schema` doesn't. For variable-length lists, use `schema`.
- **`exact` on the response body.** Will be rejected at validation time. Use `subset` (over stable keys) or `schema` (with `const` for fixed values).
- **External `$ref` in a schema.** Rejected. Inline the referenced fragments or use local `#/$defs` refs.
- **Mock response without status.** The mock object needs at least `status`. `body` and `headers` are optional.
- **Forgetting that bodies are JSON strings.** `network_request_body`, `network_mock_response`, `network_response_body` are stored as JSON-encoded strings. The frontend handles the encoding; agents authoring JSON manually must too.
- **Timeout too short for slow APIs.** Default is 15 seconds. For slow endpoints, raise up to 120s. Going beyond suggests the test should change scope.
- **Authoring `network_assertion` for download URLs.** Browser downloads bypass the normal interception path. Use [`download`](./download.md).
