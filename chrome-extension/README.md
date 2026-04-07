# Nova Act Recorder

A Chrome browser extension that records your browser interactions and converts them into ready-to-run Python scripts using the [Amazon Nova Act SDK](https://nova.amazon.com/act). Record clicks, typing, scrolling, and navigation — then export them as Python scripts or run them on the Nova Act Playground.

## Features

- **One-click recording** — Start/stop capturing browser actions with a single button
- **Smart action capture** — Clicks, typing, scrolling, form changes, copy (extract variable), navigation, and tab switches are recorded with rich element context
- **Natural language prompts** — Actions are automatically converted to human-readable prompts for Nova Act
- **Inline editing** — Review, edit, reorder (drag-and-drop), and delete recorded actions before exporting
- **Python script export** — Generate complete, runnable Python scripts using the Nova Act SDK
- **ZIP export** — Export scripts bundled with screenshots as a ZIP archive
- **Intent prompts** — Add high-level goal descriptions that export as `act_get()` + `assert` pairs
- **Run on Playground** — Send recorded scripts directly to the Nova Act Playground
- **Session persistence** — Save and reload recording sessions from Chrome local storage
- **Tab-aware recording** — Recording follows you across tabs; multi-tab sessions export as nested `with` blocks

## Installation

1. Clone or download this repository:
   ```bash
   git clone https://github.com/amazon-agi-labs/solution-nova-act-qa-studio
   cd chrome-extension
   ```

2. Open Chrome and navigate to `chrome://extensions`

3. Enable **Developer Mode** (toggle in the top-right corner)

4. Click **Load unpacked** and select the project directory (the folder containing `manifest.json`)

5. The Nova Act Recorder icon will appear in your Chrome toolbar. Click it to open the side panel.

## Quick Start

### 1. Start Recording

Click the Nova Act Recorder icon to open the side panel, then click **Start Recording**.

### 2. Perform Actions

Browse normally — click buttons, type into fields, scroll, and navigate between pages. Each interaction is captured automatically. You can also Ctrl+C / Cmd+C selected text to capture it as an extract variable step.

### 3. Stop Recording

Click **Stop Recording** in the side panel. Your actions appear in the Action Log tab.

### 4. Review the Action Log

Each recorded action shows a generated natural language prompt (e.g., `click on 'Add to Cart' button`). You can:

- **Edit** a prompt by clicking on it
- **Reorder** actions by dragging them
- **Delete** individual actions with the trash button
- **Clear all** actions with the "Clear All" button

### 5. Export a Python Script

Switch to the **Export** tab and click **Export Script**. The generated Python code appears in a text area. Click **Copy to Clipboard** to copy it.

The exported script looks like:

```python
from nova_act import NovaAct

with NovaAct(starting_page="https://example.com") as nova:
    nova.act("click on 'Search' field")
    nova.act("type 'coffee maker' into the 'Search' field")
    nova.act("click on 'Search' button")
```

You can also click **Export ZIP** to download a ZIP archive containing the Python script and any screenshots captured during recording.

## Advanced Features

### Intent Prompts

Add high-level goal descriptions to your action log:

- Click **Add Intent** in the toolbar to insert a free-text intent prompt
- Intent prompts export as `act_get()` + `assert` pairs to verify the goal was achieved

### Extract Variable (Copy)

Select text on the page and press Ctrl+C / Cmd+C during recording. This captures the selected text as an `extract_variable` action, which exports as an `act_get()` call with `STRING_SCHEMA`. When you later paste (Ctrl+V / Cmd+V) into a field, the paste action references the extracted variable using an f-string:

```python
var_1 = nova.act_get("extract the 'Order Number' text", schema=STRING_SCHEMA)
nova.act(f"type '{var_1}' into the 'Tracking Number' field")
```

### Multi-Tab Recording

When you switch between browser tabs during recording, each tab maps to a separate `NovaAct` instance. The exported script uses nested `with` blocks:

```python
with NovaAct(starting_page="https://site-a.com") as nova_1:
    with NovaAct(starting_page="https://site-b.com") as nova_2:
        nova_1.act("click on 'Copy' button")
        nova_2.act("type 'pasted text' into the 'Input' field")
```

### Run on Playground

Switch to the **Replay** tab and click **Run on Playground**. This opens the Nova Act Playground and injects your recorded actions into the editor. Check **Launch new playground tab** to open a fresh tab instead of reusing an existing one.

Note: The playground supports single-URL sessions only. Multi-tab and variable features are available in the full Python script export.

### Session Management

- **Save** — Click **Save** in the toolbar to persist the current session to Chrome local storage
- **Load** — Switch to the **Sessions** tab to view and reload saved sessions
- **Delete** — Remove saved sessions you no longer need

Sessions are stored in Chrome's local storage cache. Screenshots are not persisted with sessions to save storage space — use Export ZIP to save screenshots before switching sessions.

## Troubleshooting

### Cannot record on certain pages

Chrome extensions cannot inject content scripts into restricted pages such as:
- `chrome://` pages (settings, extensions, etc.)
- `chrome-extension://` pages
- The Chrome Web Store

Start recording on a regular web page instead.

### Storage quota warnings

Chrome local storage has a ~10MB limit. If you see a storage warning:
- Delete older saved sessions from the **Sessions** tab
- The extension checks storage usage and warns when it exceeds 90% capacity

### Actions not being captured

- Make sure recording is active in the side panel
- Recording follows you across tabs — only the currently active tab captures actions
- If the extension was reloaded during recording, you may need to start a new session

### Extension not loading

- Ensure **Developer Mode** is enabled in `chrome://extensions`
- Click **Load unpacked** and select the correct directory (must contain `manifest.json`)
- Check the Chrome DevTools console for errors

## Development

```bash
# Install dependencies
npm install

# Run all tests
npm test

# Run lint only
npm run lint

# Run lint + tests together
npm run check

# Run tests in watch mode
npm run test:watch

# Build extension ZIP for deployment
./build-extension.sh
```

## Project Structure

```
manifest.json               # Chrome Extension Manifest V3
background.js               # Service worker: message routing, session/action coordination
content.js                  # Content script: DOM event capture (clicks, typing, scrolling)
element-descriptor-core.js  # Element description functions (plain script, shared by content.js)
element-descriptor.js       # ESM wrapper re-exporting element-descriptor-core for tests
popup.html                  # Side panel UI
popup.js                    # Side panel logic, SVG icons, and message passing
popup.css                   # Side panel styles (dark theme)
types.js                    # Shared data model definitions (JSDoc typedefs)
action-store.js             # Action log CRUD operations
session-manager.js          # Recording session lifecycle
prompt-generator.js         # Action -> natural language prompt conversion
script-exporter.js          # Python script generation (single-tab and multi-tab)
storage-manager.js          # Chrome storage persistence for sessions
recording-serializer.js     # Prepares recordings for external APIs
playground-injector.js      # Content script for Nova Act Playground injection
build-extension.sh          # Build script: packages extension into a deployable ZIP
lib/jszip.min.js            # Vendored JSZip library for ZIP export
icons/                      # Extension icons (light/dark PNGs, logo SVGs)
test/                       # Vitest test suite with property-based testing (fast-check)
```

## License

This project is licensed under the MIT-0 License. See the [LICENSE](../LICENSE) file for details.
