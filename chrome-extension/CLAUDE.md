# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Nova Act Recorder is a Chrome Extension (Manifest V3) that records browser interactions and converts them into Python scripts using the Amazon Nova Act SDK. It runs as a side panel, captures clicks/typing/scrolling/navigation, and can export or replay actions.

## Commands

```bash
npm install          # Install dependencies
npm test             # Run all tests (vitest, single run)
npm run test:watch   # Run tests in watch mode
npm run lint         # ESLint on source files (*.js)
npm run check        # Lint + tests together
```

To run a single test file: `npx vitest --run test/prompt-generator.test.js`

## Architecture

**No build step.** All source files are plain ES modules (`.js`) loaded directly by Chrome. The `manifest.json` is the entry point for the extension.

### Extension layers

- **`background.js`** — Service worker and central coordinator. All message routing happens here via `chrome.runtime.onMessage` with a `message.kind` string switch. Instantiates and wires together the core modules.
- **`content.js`** — Content script injected into all pages. Captures DOM events (click, keydown, scroll) and sends `ACTION_CAPTURED` messages to background.
- **`popup.js` / `popup.html` / `popup.css`** — Side panel UI. Communicates with background via `chrome.runtime.sendMessage`.
- **`playground-injector.js`** — Content script injected only on `nova.amazon.com/*` to auto-fill the Nova Act playground editor.

### Core modules (imported by background.js)

| Module | Responsibility |
|---|---|
| `session-manager.js` | Recording lifecycle, tab-scoping, pause/resume |
| `action-store.js` | CRUD for the action log (add, delete, reorder, collapse/expand intents, extraction marking, assertions) |
| `prompt-generator.js` | Converts `RawAction` into natural language prompt strings |
| `script-exporter.js` | Generates complete Python scripts from actions |
| `storage-manager.js` | Chrome storage persistence for sessions |
| `element-descriptor-core.js` | Element description functions (plain script loaded by Chrome before content.js) |
| `element-descriptor.js` | ESM wrapper re-exporting element-descriptor-core for test imports |
| `recording-serializer.js` | Prepares recordings for external consumption by removing large/redundant fields |

### Data flow

1. `content.js` captures DOM event -> sends `ACTION_CAPTURED` to background
2. `background.js` passes raw action to `ActionStore.addAction()` (which calls `prompt-generator` internally)
3. `ActionStore` creates an `ActionEntry` with generated prompt
4. State is persisted to `chrome.storage.local` for service worker recovery
5. Popup reads state via `GET_STATE` message

### Type system

`types.js` defines all data models via JSDoc typedefs (no TypeScript). Key types: `RawAction`, `ActionEntry`, `RecordingSession`, `Assertion`, `MergeSuggestion`.

### Recorded actions

| User Interaction | DOM Event / Source | Action Type | What it records |
|---|---|---|---|
| Click on a button/link/element | `click` | `click` | Adds a "click on '<element>'" step |
| Type into an input/textarea | `focus` → `blur` / `Enter` | `type` | Adds a "type '<value>' into '<field>'" step |
| Select a dropdown/checkbox/radio | `change` | `change` | Adds a "select '<value>'" or "check/uncheck" step |
| Scroll the page or a container | `scroll` | `scroll` | Adds a "scroll up/down" step (debounced, direction-consolidated) |
| Copy selected text (Ctrl+C / Cmd+C) | `keydown` (primary) / `copy` (fallback) | `extract_variable` | Adds a variable extraction step for use in later paste references |
| Navigate to a new page | `webNavigation.onCommitted` | `navigation` | Adds a "navigate to '<url>'" step |
| Switch browser tabs | `tabs.onActivated` | `tab_switch` | Adds a "switch to tab '<title>'" step |
| IME composition (CJK input) | `compositionstart` / `compositionend` | (deferred to `type`) | Waits for composition to finish, then captures as typing |

## Message Protocol

All communication uses `chrome.runtime.sendMessage` with `{ kind: string, ... }`.

- **Recording lifecycle:** `START_RECORDING`, `STOP_RECORDING`, `START_RECORDING_FROM_CDP`, `PAGE_LOADED`, `QUERY_RECORDING_STATUS`
- **Action CRUD:** `ACTION_CAPTURED`, `GET_STATE`, `REORDER_ACTION`, `DELETE_ACTION`, `UPDATE_PROMPT`, `CLEAR_ALL`
- **Intents:** `ADD_INTENT_PROMPT`, `COLLAPSE_TO_INTENT`, `EXPAND_INTENT`
- **Assertions:** `ADD_ASSERTION`, `UPDATE_ASSERTION`, `DELETE_ASSERTION`
- **Export:** `EXPORT_SCRIPT`, `GET_RECORDING_FOR_EXPORT`, `GET_SCREENSHOTS`, `RUN_ON_PLAYGROUND`
- **Sessions:** `SAVE_SESSION`, `LOAD_SESSION`, `DELETE_SESSION`, `LIST_SESSIONS`

## Testing

- **Vitest** with `globals: true` and node environment
- Tests in `test/` directory use property-based testing via **fast-check**
- Tests mock `chrome.*` APIs since there's no browser runtime
- No TypeScript — all type checking is via JSDoc annotations

## Lint

ESLint flat config (`eslint.config.js`). Chrome globals (`chrome`, `document`, `window`, etc.) are declared as readonly. Rules focus on correctness (`no-undef`, `no-unused-vars`, `valid-typeof`).
