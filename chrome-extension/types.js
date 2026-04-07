// Nova Act Recorder - Shared Type Definitions (JSDoc)
// This module defines all data models used across the extension.

'use strict';

/**
 * Human-readable description of a DOM element derived from its attributes.
 * @typedef {Object} ElementDescriptor
 * @property {string} text - Human-readable description
 * @property {string} tagName - e.g., "button", "input"
 * @property {Object} attributes - Relevant attributes for fallback identification
 * @property {string} [attributes.id]
 * @property {string} [attributes.ariaLabel]
 * @property {string} [attributes.role]
 * @property {string} [attributes.placeholder]
 * @property {string} [attributes.name]
 * @property {string} [attributes.type]
 * @property {string} [attributes.href]
 * @property {string} [attributes.src]
 * @property {string} [attributes.alt]
 * @property {string} [attributes.value]
 * @property {string[]} [cssClasses] - CSS class list (e.g., ["btn", "btn-primary"])
 * @property {Object.<string, string>} [dataAttributes] - data-* attributes (e.g., {"testid": "submit-btn"})
 * @property {string} [outerHTML] - Truncated outer HTML of the element
 * @property {string} [ancestorPath] - Semantic ancestor chain (e.g., "nav > ul.menu > li.active")
 * @property {string} [associatedLabel] - Text of the associated <label> element
 * @property {string} [nearestHeading] - Text of the nearest heading (h1-h6) above the element
 */

/**
 * A raw captured user interaction event from the content script.
 * @typedef {Object} RawAction
 * @property {"click"|"type"|"change"|"scroll"|"navigation"|"tab_switch"|"extract_variable"|"paste"} type
 * @property {number} timestamp - Capture time (ms since epoch)
 * @property {string} url - Page URL where action occurred
 * @property {ElementDescriptor} [element] - Target element descriptor
 * @property {string} [value] - Typed text, scroll direction ("up"/"down"), or form control value
 * @property {ElementDescriptor} [scrollContainer] - For non-body scroll targets
 * @property {string} [tabTitle] - Title of the tab switched to (for tab_switch actions)
 * @property {number} [tabId] - Chrome tab ID of the destination tab (for tab_switch actions)
 * @property {string} [selectedText] - Text highlighted by the user (for extract_variable actions)
 * @property {string} [extractionLabel] - Inferred label describing the value to extract (for extract_variable actions)
 */

/**
 * A user-defined expected outcome attached to an action.
 * @typedef {Object} Assertion
 * @property {string} id - UUID
 * @property {string} text - Natural language assertion
 */


/**
 * A single entry in the action log, representing a recorded or manually added action.
 * @typedef {Object} ActionEntry
 * @property {string} id - UUID
 * @property {"click"|"type"|"change"|"scroll"|"navigation"|"tab_switch"|"intent"|"extract_variable"|"paste"} type
 * @property {RawAction} [rawAction] - Original captured action (absent for manually added intents)
 * @property {string} prompt - Generated or user-edited prompt text
 * @property {boolean} promptEdited - Whether the user has manually edited the prompt
 * @property {string} url - Page URL where action occurred
 * @property {number} timestamp - Capture time (ms since epoch)
 * @property {boolean} isIntent - Whether this is a high-level intent prompt
 * @property {ActionEntry[]} [collapsedActions] - Original actions if this is a collapsed intent
 * @property {Assertion[]} assertions - Assertions attached to this action
 * @property {string} [variableName] - Auto-generated variable name (for extract_variable actions)
 * @property {string} [selectedText] - User-highlighted text (for extract_variable actions)
 * @property {string} [sourceVariableName] - Variable name from last extract_variable (for paste actions)
 */

/**
 * A time-bounded sequence of actions captured between start and stop.
 * @typedef {Object} RecordingSession
 * @property {string} id - UUID
 * @property {number} startedAt - Timestamp
 * @property {number} [stoppedAt] - Timestamp
 * @property {number} tabId - Chrome tab ID where recording started
 * @property {string} startingUrl - Initial page URL
 * @property {ActionEntry[]} actions - Ordered action log
 */

/**
 * Summary of a saved session for listing purposes.
 * @typedef {Object} SessionSummary
 * @property {string} id
 * @property {number} startedAt
 * @property {number} [stoppedAt]
 * @property {string} startingUrl
 * @property {number} actionCount
 */

/**
 * A suggestion to merge consecutive actions into a single prompt.
 * @typedef {Object} MergeSuggestion
 * @property {number} startIndex
 * @property {number} endIndex
 * @property {string} mergedPrompt
 * @property {string} reason - e.g., "type + click search = search for"
 */


/**
 * Information about Chrome local storage usage.
 * @typedef {Object} StorageQuotaInfo
 * @property {number} bytesUsed
 * @property {number} bytesTotal - chrome.storage.local quota (typically 10MB)
 * @property {number} percentUsed
 */

/**
 * A session prepared for export to a Python script.
 * @typedef {Object} ExportableSession
 * @property {string} startingUrl
 * @property {number} [startingTabId] - Chrome tab ID of the initial recording tab
 * @property {ActionEntry[]} actions
 */
