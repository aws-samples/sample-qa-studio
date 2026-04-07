// Nova Act Recorder - Content Script
// Injected into web pages to capture DOM events (click, input, scroll, navigation)
//
// ARCHITECTURE: Listeners are attached ONCE on script load and never detached.
// The `isRecording` flag gates whether captured events are sent to background.
// This avoids the fragile attach/detach lifecycle that caused missed events
// after tab switches, navigation, and service worker restarts.
//
// ENHANCEMENTS (based on rrweb & Playwright research):
// - Composition events for IME input (Chinese, Japanese, Korean, etc.)
// - Change events for form controls (select, checkbox, radio)
// - Shadow DOM support via event.composedPath()
// - Synthetic event filtering via event.isTrusted

'use strict';

let isRecording = false;
let scrollTimeout = null;
let lastScrollDirection = null;
let lastScrollContainer = null;
let activeInputElement = null;
let inputValueOnFocus = '';
let lastClickTimestamp = 0;
let lastClickTarget = null;
let isComposing = false; // Track IME composition state
let compositionElement = null;
let lastCopyTimestamp = 0; // Dedup between keydown Ctrl+C and copy event
let valueBeforeInput = null; // Captures pre-edit value via beforeinput event

// WeakMap to track scroll positions for direction detection via scroll events
const scrollPositions = new WeakMap();

// Element descriptor functions (extractElementDescriptor, getAssociatedLabel, getNearestHeading, etc.)
// are loaded from element-descriptor-core.js via manifest.json and available as globals.

// ─── Event Utilities ───

/**
 * Gets the true event target, handling shadow DOM boundaries.
 * Uses event.composedPath() to traverse shadow DOM boundaries.
 * @param {Event} event
 * @returns {Element}
 */
function getEventTarget(event) {
  // composedPath() returns the event's path including shadow DOM nodes
  if (event.composedPath && event.composedPath().length > 0) {
    return event.composedPath()[0];
  }
  return event.target;
}

/**
 * Checks if an event is trusted (user-initiated, not programmatic).
 * @param {Event} event
 * @returns {boolean}
 */
function isTrustedEvent(event) {
  // event.isTrusted is true for user-initiated events, false for synthetic/programmatic
  return event.isTrusted !== false;
}

/**
 * Checks if an element is likely interactive (clickable on purpose).
 * Used to filter out accidental clicks on layout containers like <div>, <section>, etc.
 * An element is considered interactive if it:
 * - Is an inherently interactive HTML element (button, a, select, summary, details)
 * - Has an interactive ARIA role
 * - Has a tabindex attribute (intentionally made focusable)
 * - Has an onclick attribute
 * - Has short text content (likely a custom button/card, not a layout container)
 * @param {Element} element
 * @returns {boolean}
 */
function isInteractiveElement(element) {
  const tag = element.tagName.toLowerCase();

  // Inherently interactive elements
  const interactiveTags = new Set(['button', 'a', 'select', 'summary', 'details', 'option']);
  if (interactiveTags.has(tag)) return true;

  // Interactive input types
  if (tag === 'input' && ['submit', 'button', 'checkbox', 'radio', 'file', 'image'].includes(element.type)) {
    return true;
  }

  // ARIA role indicates interactivity
  const role = element.getAttribute('role');
  if (role) {
    const interactiveRoles = new Set([
      'button', 'link', 'tab', 'menuitem', 'menuitemcheckbox', 'menuitemradio',
      'option', 'radio', 'switch', 'checkbox', 'treeitem', 'gridcell',
    ]);
    if (interactiveRoles.has(role)) return true;
  }

  // Explicit tabindex means intentionally focusable
  if (element.hasAttribute('tabindex')) return true;

  // Inline onclick handler
  if (element.hasAttribute('onclick')) return true;

  // Short text content — likely a custom button/card, not a layout container
  const text = (element.textContent || '').trim();
  if (text.length > 0 && text.length <= 200) return true;

  return false;
}

// ─── Click Handler ───

function handleClick(event) {
  if (!isRecording) return;
  if (!isTrustedEvent(event)) return;

  // Flush pending typing before processing click (unless clicking the active input itself)
  const clickedEl = getEventTarget(event);
  flushPendingTyping(clickedEl);

  // Walk up to the nearest meaningful clickable element (button, a, input, etc.)
  let element = clickedEl;
  const clickableParent = element.closest('button, a, [role="button"], input[type="submit"], input[type="button"]');
  if (clickableParent) {
    element = clickableParent;
  }

  // Deduplicate: ignore clicks on the same element within 100ms (bubbling duplicates)
  const now = Date.now();
  if (element === lastClickTarget && now - lastClickTimestamp < 100) {
    return;
  }
  lastClickTimestamp = now;
  lastClickTarget = element;

  // Don't record clicks on input/textarea — those are typing targets, not click actions
  const tag = element.tagName.toLowerCase();
  if (tag === 'input' && !['submit', 'button', 'checkbox', 'radio', 'file'].includes(element.type)) {
    return;
  }
  if (tag === 'textarea') {
    return;
  }

  // Don't record clicks on <label> elements — the browser forwards the click to the
  // associated input (via `for` attribute or wrapping), which will be recorded instead.
  if (tag === 'label') {
    if (element.htmlFor || element.querySelector('input, select, textarea')) {
      return;
    }
  }

  // Skip clicks on non-interactive layout containers (e.g., clicking the gap
  // between form fields). Without this, we'd record "click on '<entire page text>'"
  // which is useless for Nova Act.
  if (!clickableParent && !isInteractiveElement(element)) {
    return;
  }

  const descriptor = extractElementDescriptor(element);

  /** @type {import('./types.js').RawAction} */
  const action = {
    type: 'click',
    timestamp: now,
    url: window.location.href,
    element: descriptor,
  };

  sendActionToBackground(action);
}

// ─── Typing Handlers ───
// Handles focus/blur/input for standard typing, plus composition events for IME input.

function handleFocus(event) {
  if (!isRecording) return;
  const el = event.target;
  if (isTypingTarget(el)) {
    activeInputElement = el;
    inputValueOnFocus = el.isContentEditable
      ? (el.textContent || '').trim()
      : (el.value || '');

    // If we're in the middle of composition, track that
    if (isComposing && compositionElement !== el) {
      // Composition ended on previous element without blur
      isComposing = false;
      compositionElement = null;
    }
  }
}

function handleBlur(event) {
  if (!isRecording) return;
  const el = event.target;
  if (isTypingTarget(el) && el === activeInputElement) {
    captureTypingAction(el);
    activeInputElement = null;

    // End composition if active
    if (isComposing && compositionElement === el) {
      isComposing = false;
      compositionElement = null;
    }
  }
}

function handleKeydown(event) {
  if (!isRecording) return;

  // Detect Ctrl+C / Cmd+C for extract_variable capture.
  // Chrome does not reliably dispatch the 'copy' DOM event to content scripts,
  // so we detect the keyboard shortcut directly via keydown which always fires.
  if ((event.ctrlKey || event.metaKey) && event.key === 'c') {
    captureExtractVariable();
  }

  if (event.key === 'Enter') {
    const el = event.target;
    if (isTypingTarget(el) && el === activeInputElement) {
      captureTypingAction(el);
      activeInputElement = null;
    }
  }
}

// ─── Composition Event Handlers (IME Input) ───
// Critical for international users typing in Chinese, Japanese, Korean, etc.
// During composition, input events fire but we shouldn't capture until composition ends.

function handleCompositionStart(event) {
  if (!isRecording) return;
  const el = event.target;
  if (isTypingTarget(el)) {
    isComposing = true;
    compositionElement = el;

    // If this is a new element, set it as active
    if (activeInputElement !== el) {
      activeInputElement = el;
      inputValueOnFocus = el.isContentEditable
        ? (el.textContent || '').trim()
        : (el.value || '');
    }
  }
}

function handleCompositionEnd(event) {
  if (!isRecording) return;
  const el = event.target;

  if (isTypingTarget(el) && el === compositionElement) {
    isComposing = false;
    compositionElement = null;

    // Capture the composed text
    // The input event will fire after this, so we update inputValueOnFocus
    // to avoid double-capturing
    const currentValue = el.isContentEditable
      ? (el.textContent || '').trim()
      : (el.value || '');

    if (currentValue && currentValue !== inputValueOnFocus) {
      // Update the baseline so subsequent input events see this as the starting point
      inputValueOnFocus = currentValue;

      // Note: We rely on blur or Enter to actually send the action.
      // This just ensures the composed text is included in the final capture.
      // If you want to capture each composition immediately, call captureTypingAction(el) here.
    }
  }
}

/**
 * Captures the final value of an input element as a single typing action.
 * Only captures if the value actually changed from what it was at focus time.
 * @param {Element} el
 */
function captureTypingAction(el) {
  const value = el.isContentEditable
    ? (el.textContent || '').trim()
    : (el.value || '');

  if (value === inputValueOnFocus) return;

  const descriptor = extractElementDescriptor(el);

  /** @type {import('./types.js').RawAction} */
  const action = {
    type: 'type',
    timestamp: Date.now(),
    url: window.location.href,
    element: descriptor,
    value: value,
  };

  sendActionToBackground(action);
}

/**
 * Checks if an element is a valid typing target (input, textarea, or contenteditable).
 * @param {Element} el
 * @returns {boolean}
 */
function isTypingTarget(el) {
  if (!el || !el.tagName) return false;
  const tag = el.tagName.toLowerCase();
  if (tag === 'textarea') return true;
  if (el.isContentEditable) return true;
  if (tag === 'input') {
    const type = (el.type || 'text').toLowerCase();
    return ['text', 'password', 'email', 'search', 'url', 'tel', 'number'].includes(type);
  }
  return false;
}

// ─── Typing Recovery via Input Events ───
// Also handles composition state to avoid capturing during IME input.

/**
 * Recovers activeInputElement tracking when we missed a focus event
 * (e.g. after tab switch, service worker restart, or page navigation during recording).
 * Also fires on every keystroke, so it catches cases where focus was already
 * in the element before recording started.
 *
 * IMPORTANT: During IME composition (isComposing=true), input events fire but we
 * shouldn't capture yet — wait for compositionend.
 */
/**
 * Captures the element's value BEFORE the edit is applied.
 * Used by handleInput to detect when a field is cleared to empty.
 */
function handleBeforeInput(event) {
  if (!isRecording) return;
  if (isComposing) return;
  const el = event.target;
  if (!isTypingTarget(el)) return;
  valueBeforeInput = el.isContentEditable
    ? (el.textContent || '').trim()
    : (el.value || '');
}

function handleInput(event) {
  if (!isRecording) return;

  // Don't capture during composition — wait for compositionend
  if (isComposing) return;

  const el = event.target;
  if (!isTypingTarget(el)) return;

  // Recovery: if we missed the focus event, start tracking this element
  if (activeInputElement !== el) {
    activeInputElement = el;
    // Use current value as baseline (already one keystroke past the original)
    inputValueOnFocus = el.isContentEditable
      ? (el.textContent || '').trim()
      : (el.value || '');
  }

  // Detect field cleared to empty via Backspace/Delete.
  // Uses valueBeforeInput (captured in beforeinput) so this works regardless
  // of whether inputValueOnFocus was reset by scroll flush or recovery.
  const currentValue = el.isContentEditable
    ? (el.textContent || '').trim()
    : (el.value || '');
  if (currentValue === '' && valueBeforeInput && valueBeforeInput !== '') {
    // Set inputValueOnFocus to the pre-edit value so captureTypingAction sees
    // a real change. Without this, the recovery path above may have already
    // set inputValueOnFocus to '' (the post-edit value), causing the action
    // to be silently dropped.
    inputValueOnFocus = valueBeforeInput;
    captureTypingAction(el);
    // Update baseline so blur doesn't double-capture
    inputValueOnFocus = '';
  }
  valueBeforeInput = null;
}

// ─── Change Event Handler ───
// Fires when a form control value is committed (blur for text inputs, selection for dropdowns).
// Critical for <select>, checkbox, radio, and other form controls where click doesn't convey the value.

function handleChange(event) {
  if (!isRecording) return;
  if (!isTrustedEvent(event)) return;

  flushPendingTyping();

  const el = event.target;
  const tag = el.tagName.toLowerCase();

  // For text inputs, input+blur already handle this — skip to avoid duplicates
  if (tag === 'input') {
    const type = (el.type || 'text').toLowerCase();
    // Skip text inputs (handled by input+blur)
    if (['text', 'password', 'email', 'search', 'url', 'tel', 'number'].includes(type)) {
      return;
    }
    // Skip checkbox/radio — already captured by the click handler
    if (type === 'checkbox' || type === 'radio') {
      return;
    }
  }

  // For textarea, input+blur already handle this
  if (tag === 'textarea') return;

  // Capture for: select, checkbox, radio, file, range, color, etc.
  const descriptor = extractElementDescriptor(el);

  let value = '';
  if (tag === 'select') {
    const selectedOption = el.options[el.selectedIndex];
    value = selectedOption ? selectedOption.text : el.value;
  } else if (el.type === 'checkbox' || el.type === 'radio') {
    value = el.checked ? 'checked' : 'unchecked';
  } else if (el.type === 'file') {
    value = el.files.length > 0 ? Array.from(el.files).map(f => f.name).join(', ') : '';
  } else {
    value = el.value || '';
  }

  /** @type {import('./types.js').RawAction} */
  const action = {
    type: 'change',
    timestamp: Date.now(),
    url: window.location.href,
    element: descriptor,
    value: value,
  };

  sendActionToBackground(action);
}

// ─── Extraction Label Detection ───
// Heuristics to find a human-readable label for the value the user selected.
// This produces better nova.act_get() prompts: instead of describing the element
// containing the value, we describe what the value IS (e.g., "Transit Time"
// instead of "13.7 yrs / 3 days").

/**
 * Finds a descriptive label for the selected text by inspecting DOM context.
 * Tries strategies in order of specificity and returns the first match.
 * @param {Element} element - The element containing (or closest to) the selection
 * @param {string} selectedText - The text the user highlighted
 * @returns {string|undefined} A label string, or undefined if no good label was found
 */
function findLabelForSelection(element, selectedText) {
  return findSiblingLabel(element, selectedText)
    || findInlineLabel(element, selectedText)
    || findTableLabel(element)
    || findAriaLabelAncestor(element)
    || getAssociatedLabel(element)
    || getNearestHeading(element)
    || undefined;
}

/**
 * Looks for a previous sibling element whose text looks like a label.
 * Handles: <span class="label">Transit Time</span><span class="value">13.7 yrs</span>
 * Walks up to 3 ancestor levels, checking previous siblings at each.
 * @param {Element} element
 * @param {string} selectedText
 * @returns {string|undefined}
 */
function findSiblingLabel(element, selectedText) {
  let current = element;
  for (let depth = 0; depth < 3 && current; depth++) {
    let sibling = current.previousElementSibling;
    while (sibling) {
      const siblingText = (sibling.textContent || '').trim();
      // A good label: non-empty, reasonably short, and not the value itself
      if (siblingText
        && siblingText.length <= 100
        && siblingText !== selectedText
        && !siblingText.includes(selectedText)) {
        return siblingText;
      }
      sibling = sibling.previousElementSibling;
    }
    current = current.parentElement;
    if (!current || current.tagName === 'BODY' || current.tagName === 'HTML') break;
  }
  return undefined;
}

/**
 * Detects "Label: Value" or "Label - Value" patterns within the same element.
 * Handles: <span>Transit Time: 13.7 yrs</span>
 * @param {Element} element
 * @param {string} selectedText
 * @returns {string|undefined}
 */
function findInlineLabel(element, selectedText) {
  const fullText = (element.textContent || '').trim();
  if (!fullText || !fullText.includes(selectedText)) return undefined;

  const separators = [':', ' - ', ' \u2013 ', ' \u2014 '];
  for (const sep of separators) {
    const sepIndex = fullText.indexOf(sep);
    if (sepIndex === -1) continue;

    const before = fullText.substring(0, sepIndex).trim();
    const after = fullText.substring(sepIndex + sep.length).trim();

    // If the selected text is in the part after the separator, the part before is the label
    if (after.includes(selectedText) && before.length > 0 && before.length <= 100) {
      return before;
    }
  }
  return undefined;
}

/**
 * Finds the label from a table header (<th>) or definition term (<dt>).
 * Handles: <tr><th>Name</th><td>Value</td></tr> and <dl><dt>Name</dt><dd>Value</dd></dl>
 * @param {Element} element
 * @returns {string|undefined}
 */
function findTableLabel(element) {
  // Check <td> → corresponding <th>
  const td = element.closest ? element.closest('td') : null;
  if (td) {
    const cellIndex = td.cellIndex;
    const row = td.parentElement;
    // Check for <th> in the same row (label column pattern)
    if (row) {
      const th = row.querySelector('th');
      if (th) {
        const text = (th.textContent || '').trim();
        if (text) return text;
      }
    }
    // Check for <th> in the header row at the same column index
    const table = td.closest ? td.closest('table') : null;
    if (table && cellIndex >= 0) {
      const headerRow = table.querySelector('thead tr') || table.querySelector('tr');
      if (headerRow && headerRow !== row) {
        const headerCells = headerRow.cells || headerRow.querySelectorAll('th, td');
        if (headerCells[cellIndex]) {
          const text = (headerCells[cellIndex].textContent || '').trim();
          if (text) return text;
        }
      }
    }
  }

  // Check <dd> → preceding <dt>
  const dd = element.closest ? element.closest('dd') : null;
  if (dd) {
    let prev = dd.previousElementSibling;
    while (prev) {
      if (prev.tagName === 'DT') {
        const text = (prev.textContent || '').trim();
        if (text) return text;
      }
      prev = prev.previousElementSibling;
    }
  }

  return undefined;
}

/**
 * Walks up the ancestor chain looking for an aria-label attribute.
 * Skips the element itself (that's already in the descriptor).
 * @param {Element} element
 * @returns {string|undefined}
 */
function findAriaLabelAncestor(element) {
  // Check the element itself first
  const selfLabel = element.getAttribute ? element.getAttribute('aria-label') : null;
  if (selfLabel) return selfLabel;

  // Walk up ancestors
  let current = element.parentElement;
  for (let depth = 0; depth < 5 && current; depth++) {
    const label = current.getAttribute ? current.getAttribute('aria-label') : null;
    if (label) return label;
    current = current.parentElement;
    if (!current || current.tagName === 'BODY' || current.tagName === 'HTML') break;
  }
  return undefined;
}

// ─── Copy / Extract Variable ───
// Captures Ctrl+C / Cmd+C with text selected and sends extract_variable actions.
// Called from both keydown (primary, always fires) and the copy DOM event (fallback).

/**
 * Captures the current text selection as an extract_variable action.
 * Deduplicates so that if both keydown and copy event fire, only one action is sent.
 * @returns {boolean} true if an action was sent
 */
function captureExtractVariable() {
  flushPendingTyping();

  // Deduplicate: skip if we already captured within the last 200ms
  const now = Date.now();
  if (now - lastCopyTimestamp < 200) return false;

  // Try to get selected text — window.getSelection() doesn't work for
  // <input> and <textarea>, so we check the focused element first.
  let selectedText = '';
  let ancestor = null;

  const focused = document.activeElement;
  if (focused && (focused.tagName === 'INPUT' || focused.tagName === 'TEXTAREA')
    && typeof focused.selectionStart === 'number'
    && typeof focused.selectionEnd === 'number'
    && focused.selectionStart !== focused.selectionEnd) {
    selectedText = (focused.value || '').substring(focused.selectionStart, focused.selectionEnd).trim();
    ancestor = focused;
  } else {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) return false;
    selectedText = selection.toString().trim();
    if (!selectedText) return false;
    const range = selection.getRangeAt(0);
    ancestor = range.commonAncestorContainer;
    // If the ancestor is a text node (nodeType 3), use its parent element
    if (ancestor.nodeType === 3) {
      ancestor = ancestor.parentElement;
    }
  }

  if (!selectedText) return false;
  if (!ancestor || !ancestor.tagName) return false;

  lastCopyTimestamp = now;

  const descriptor = extractElementDescriptor(ancestor);

  // Try to find a descriptive label for what the user is extracting
  const extractionLabel = findLabelForSelection(ancestor, selectedText);

  /** @type {import('./types.js').RawAction} */
  const action = {
    type: 'extract_variable',
    timestamp: now,
    url: window.location.href,
    element: descriptor,
    selectedText: selectedText,
  };

  if (extractionLabel) {
    action.extractionLabel = extractionLabel;
  }

  sendActionToBackground(action);
  return true;
}

/**
 * Fallback handler for the copy DOM event.
 * In Chrome the copy event may not fire reliably in content scripts,
 * so keydown Ctrl+C is the primary detection path.
 */
function handleCopy(event) {
  if (!isRecording) return;
  if (!isTrustedEvent(event)) return;
  captureExtractVariable();
}

// ─── Paste Handler ───
// Captures Ctrl+V / Cmd+V paste events and sends them as paste actions.
// Links to the last extract_variable (copy) in the action store.

function handlePaste(event) {
  if (!isRecording) return;
  if (!isTrustedEvent(event)) return;

  flushPendingTyping();

  const el = getEventTarget(event);
  if (!el || !el.tagName) return;

  // Get the pasted text from the clipboard data
  const pastedText = event.clipboardData
    ? event.clipboardData.getData('text/plain')
    : '';
  if (!pastedText) return;

  const descriptor = extractElementDescriptor(el);

  /** @type {import('./types.js').RawAction} */
  const action = {
    type: 'paste',
    timestamp: Date.now(),
    url: window.location.href,
    element: descriptor,
    value: pastedText,
  };

  sendActionToBackground(action);

  // Re-track the element and update baseline so blur doesn't generate a
  // duplicate type action for the pasted content.
  // flushPendingTyping() above set activeInputElement = null, so we must
  // re-assign it. Then use a microtask to read the value after the browser
  // has applied the paste.
  if (isTypingTarget(el)) {
    activeInputElement = el;
    Promise.resolve().then(() => {
      inputValueOnFocus = el.isContentEditable
        ? (el.textContent || '').trim()
        : (el.value || '');
    });
  }
}

// ─── Scroll Handler ───
// Uses the native 'scroll' event instead of 'wheel' to capture ALL scroll sources:
// mouse wheel, keyboard (Space, PageDown, arrows), touch swipe, and programmatic scrolls.

function handleScroll(event) {
  if (!isRecording) return;

  flushPendingTyping();

  // Determine the scrolling element
  const target = event.target === document
    ? document.documentElement
    : event.target;

  if (!target || typeof target.scrollTop !== 'number') return;

  const currentTop = target.scrollTop;
  const previousTop = scrollPositions.get(target);

  // First scroll event for this element — just record position, don't emit action
  if (previousTop === undefined) {
    scrollPositions.set(target, currentTop);
    return;
  }

  // No actual movement
  if (currentTop === previousTop) return;

  const direction = currentTop > previousTop ? 'down' : 'up';
  scrollPositions.set(target, currentTop);

  const isBodyScroll = target === document.body || target === document.documentElement;
  const containerDescriptor = isBodyScroll ? undefined : extractElementDescriptor(target);

  // Same-direction consolidation with debounce
  if (scrollTimeout && lastScrollDirection === direction && isSameContainer(lastScrollContainer, containerDescriptor)) {
    clearTimeout(scrollTimeout);
  } else if (scrollTimeout && (lastScrollDirection !== direction || !isSameContainer(lastScrollContainer, containerDescriptor))) {
    clearTimeout(scrollTimeout);
    flushScrollAction();
  }

  lastScrollDirection = direction;
  lastScrollContainer = containerDescriptor;

  scrollTimeout = setTimeout(() => {
    flushScrollAction();
  }, 300);
}

function flushScrollAction() {
  if (!lastScrollDirection) return;

  /** @type {import('./types.js').RawAction} */
  const action = {
    type: 'scroll',
    timestamp: Date.now(),
    url: window.location.href,
    value: lastScrollDirection,
  };

  if (lastScrollContainer) {
    action.scrollContainer = lastScrollContainer;
  }

  sendActionToBackground(action);

  lastScrollDirection = null;
  lastScrollContainer = null;
  scrollTimeout = null;
}

/**
 * Compares two container descriptors for equality.
 */
function isSameContainer(a, b) {
  if (!a && !b) return true;
  if (!a || !b) return false;
  return a.text === b.text && a.tagName === b.tagName;
}

// ─── Flush Pending Actions ───

/**
 * Flushes any pending typing action (e.g. before a click, paste, or stop).
 * @param {Element} [excludeElement] - If provided, skip flushing if the active input IS this element.
 */
function flushPendingTyping(excludeElement) {
  if (activeInputElement && isTypingTarget(activeInputElement)) {
    if (excludeElement && activeInputElement === excludeElement) return;
    captureTypingAction(activeInputElement);
    activeInputElement = null;
  }
}

/**
 * Flushes any in-flight typing or scroll actions.
 * Called on STOP_RECORDING and beforeunload to prevent data loss.
 */
function flushPendingActions() {
  flushPendingTyping();
  // Flush pending scroll
  if (scrollTimeout) {
    clearTimeout(scrollTimeout);
    flushScrollAction();
  }
}

// ─── Message Passing ───

/**
 * Sends a captured action to the background service worker.
 * Retries once if the service worker is waking up.
 * @param {import('./types.js').RawAction} action
 */
function sendActionToBackground(action) {
  try {
    chrome.runtime.sendMessage({ kind: 'ACTION_CAPTURED', action }, () => {
      if (chrome.runtime.lastError) {
        // Service worker may be waking up — retry once after a short delay
        setTimeout(() => {
          try {
            chrome.runtime.sendMessage({ kind: 'ACTION_CAPTURED', action }, () => {
              // Suppress any further errors — we did our best
              void chrome.runtime.lastError;
            });
          } catch {
            // Extension context invalidated — nothing we can do
          }
        }, 100);
      }
    });
  } catch {
    // Extension context invalidated (e.g. extension updated/reloaded)
  }
  // Broadcast to page context for CDP to read
  window.postMessage({ type: 'NOVA_RECORDER_ACTION', action }, '*');
}

/**
 * Notifies the background that the page has loaded and asks for recording status.
 */
function sendPageLoaded() {
  try {
    chrome.runtime.sendMessage({ kind: 'PAGE_LOADED', url: window.location.href }, (response) => {
      if (chrome.runtime.lastError) return;
      // Background tells us whether this tab should be recording
      if (response && typeof response.shouldRecord === 'boolean') {
        isRecording = response.shouldRecord;
      }
    });
  } catch {
    // Extension context invalidated
  }
}

// ─── Always-On Event Listeners ───
// Attached once on script load and never removed. The isRecording flag
// gates whether events are processed. This eliminates the entire class of
// bugs caused by detach/reattach cycles (missed focus, lost activeInputElement, etc.)

// Click events
document.addEventListener('click', handleClick, true);

// Typing events
document.addEventListener('focus', handleFocus, true);
document.addEventListener('blur', handleBlur, true);
document.addEventListener('keydown', handleKeydown, true);
document.addEventListener('beforeinput', handleBeforeInput, true);
document.addEventListener('input', handleInput, true);
document.addEventListener('change', handleChange, true);

// Composition events (IME input for international users)
document.addEventListener('compositionstart', handleCompositionStart, true);
document.addEventListener('compositionend', handleCompositionEnd, true);

// Copy events (extract variable on Ctrl+C / Cmd+C)
document.addEventListener('copy', handleCopy, true);

// Paste events (Ctrl+V / Cmd+V)
document.addEventListener('paste', handlePaste, true);

// Scroll events
document.addEventListener('scroll', handleScroll, { passive: true, capture: true });

// ─── Flush on Navigation ───
// Captures in-flight typing/scroll when the user navigates away from the page.

window.addEventListener('beforeunload', () => {
  if (isRecording) {
    flushPendingActions();
  }
});

// ─── State Sync on Visibility Change ───
// When the user switches back to this tab, re-sync recording status with background.
// Handles service worker restarts and tab switch races.

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState !== 'visible') return;
  try {
    chrome.runtime.sendMessage({ kind: 'QUERY_RECORDING_STATUS' }, (response) => {
      if (chrome.runtime.lastError) return;
      if (response && typeof response.shouldRecord === 'boolean') {
        isRecording = response.shouldRecord;
      }
    });
  } catch {
    // Extension context invalidated
  }
});

// ─── Message Handlers ───

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.kind) {
    case 'START_RECORDING':
      isRecording = true;
      sendResponse({ success: true });
      break;
    case 'STOP_RECORDING':
      flushPendingActions();
      isRecording = false;
      sendResponse({ success: true });
      break;
    case 'RECORDING_STATUS':
      sendResponse({ isRecording });
      break;
    case 'BROADCAST_ACTION':
      // Forward a background-originated action to the page context
      // so the CDP collector (window.__novaActions) can pick it up.
      window.postMessage({ type: 'NOVA_RECORDER_ACTION', action: message.action }, '*');
      sendResponse({ success: true });
      break;
    case 'BROADCAST_ENTRY':
      // Forward a full ActionEntry (with id/prompt) to the page context
      // so the CDP collector gets complete entries for use case generation.
      window.postMessage({ type: 'NOVA_RECORDER_ENTRY', entry: message.entry }, '*');
      sendResponse({ success: true });
      break;
    case 'BROADCAST_SCREENSHOT':
      // Forward screenshot to page context for CDP collector
      window.postMessage({
        type: 'NOVA_RECORDER_SCREENSHOT',
        actionId: message.actionId,
        dataUrl: message.dataUrl,
      }, '*');
      sendResponse({ success: true });
      break;
    default:
      break;
  }
  return false;
});

// ─── CDP Bridge: window.postMessage ↔ chrome.runtime.sendMessage ───

// Listen for external commands via window.postMessage (CDP bridge)
// This allows headless control of the extension via Chrome DevTools Protocol.
// CDP Runtime.evaluate runs in the page's main world where chrome.runtime is
// undefined, so we relay commands through the content script's isolated world.
window.addEventListener('message', (event) => {
  if (event.source !== window) return;
  if (!event.data || event.data.type !== 'NOVA_RECORDER_CMD') return;

  const { command, payload } = event.data;
  chrome.runtime.sendMessage(
    { kind: command, ...(payload || {}), url: window.location.href },
    (response) => {
      window.postMessage({ type: 'NOVA_RECORDER_RESPONSE', command, response }, '*');
    }
  );
});

// Notify background that page has loaded and get recording status
sendPageLoaded();

// ─── CDP Bridge Functions (Legacy) ───
// Exposed on `window` so the ECS worker can invoke them via CDP Runtime.evaluate.
// These are the primary entry points for remote recording control.

/**
 * Starts recording via CDP. Sends START_RECORDING to the background service worker
 * which initializes the session and tells this content script to begin capturing.
 * @returns {Promise<{success: boolean, error?: string}>}
 */
window.__novaRecorderStartRecording = function () {
  return new Promise((resolve) => {
    try {
      // Get the active tab's URL and ID from the background
      chrome.runtime.sendMessage({ kind: 'GET_STATE' }, (stateResponse) => {
        if (chrome.runtime.lastError) {
          resolve({ success: false, error: chrome.runtime.lastError.message });
          return;
        }
        // Use current page URL and request background to start recording on this tab
        // The tabId is not directly available in content scripts, so we send a
        // START_RECORDING_FROM_CDP message that the background resolves using sender.tab.id
        chrome.runtime.sendMessage(
          { kind: 'START_RECORDING_FROM_CDP', url: window.location.href },
          (response) => {
            if (chrome.runtime.lastError) {
              resolve({ success: false, error: chrome.runtime.lastError.message });
            } else if (response && response.success) {
              isRecording = true;
              resolve({ success: true });
            } else {
              resolve({ success: false, error: (response && response.error) || 'Failed to start recording' });
            }
          }
        );
      });
    } catch (e) {
      resolve({ success: false, error: e.message });
    }
  });
};

/**
 * Stops recording via CDP. Flushes pending actions, then sends STOP_RECORDING to
 * the background which returns the serialized (stripped) RecordingSession.
 * @returns {Promise<{success: boolean, data?: object, error?: string}>}
 */
window.__novaRecorderStopRecording = function () {
  return new Promise((resolve) => {
    try {
      // Flush any in-flight typing/scroll actions before stopping
      flushPendingActions();
      isRecording = false;

      chrome.runtime.sendMessage({ kind: 'STOP_RECORDING' }, (response) => {
        if (chrome.runtime.lastError) {
          resolve({ success: false, error: chrome.runtime.lastError.message });
        } else if (response && response.success) {
          resolve({ success: true, data: response.session });
        } else {
          resolve({ success: false, error: (response && response.error) || 'Failed to stop recording' });
        }
      });
    } catch (e) {
      resolve({ success: false, error: e.message });
    }
  });
};

// Export for testing (Node.js / Vitest environment)
