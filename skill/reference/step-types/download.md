# download

Triggers and verifies a file download. The action that triggers the download is described in `instruction`; the file is captured and uploaded to S3 (in remote mode) or kept in the local artifacts directory (in `--local-only` mode).

## When to use

- **Verifying a download button works** — e.g., the "Download CSV" button on a reports page.
- **Capturing a downloaded file** for inspection by a later step or for human review.
- **Testing an export flow** end-to-end (click "Export", file appears, file has expected content type).

## When NOT to use

- **Reading the file's content** as part of the test. The download step verifies the download happened; it does not parse the contents. If the test needs to inspect the body, do that out-of-band.
- **Anything other than file downloads.** A button click that triggers a non-download action belongs in [`navigation`](./navigation.md).
- **An API call that returns a file.** Use [`network_assertion`](./network_assertion.md) if the test cares about the HTTP request shape; the response body assertion can validate JSON/XML responses.

## Inputs

| Field | Type | Required | Purpose |
|---|---|---|---|
| `step_type` | string | yes | `"download"`. |
| `instruction` | string | yes | Natural-language description of how to trigger the download (e.g. `"Click the 'Download Report' button"`). |

## Output

The downloaded file is stored as an artifact alongside other test outputs. In `--local-only` mode, files land under `~/.qa-studio/artifacts/<usecase-id>/downloads/`. In remote mode, files are uploaded to S3 with the execution record.

## Examples

Trigger and verify a download:

```json
{
  "step_type": "download",
  "instruction": "Click the 'Download CSV' button in the report header"
}
```

Download after navigating to the relevant page:

```json
{
  "step_type": "browser",
  "browser_action": "navigate",
  "browser_args": "{\"url\": \"/reports/sales\"}"
}
```

```json
{
  "step_type": "download",
  "instruction": "Click the export button and confirm in the dialog if it appears"
}
```

## Common pitfalls

- **No actual download.** If the click doesn't trigger a real browser download (e.g., the link opens a PDF inline rather than downloading), the step fails. Verify the page actually downloads.
- **Trying to validate the content.** The step only verifies that a download occurred. Any content checks must be performed out-of-band against the saved artifact, not as part of the test.
- **Multi-file downloads.** Each `download` step expects exactly one file. If the action triggers a zip with multiple files, that's still one download (the zip itself).
- **Confusing with `network_assertion`.** A click that returns a JSON response intercepted by the browser is not a download; use `network_assertion` to verify HTTP shape, or [`validation`](./validation.md) to check the rendered result.
