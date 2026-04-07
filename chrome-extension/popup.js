// Nova Act Recorder - Popup UI
// Communicates with background service worker via chrome.runtime.sendMessage

'use strict';

// ─── State ───

let currentActions = [];
let isRecording = false;
let dragSourceIndex = null;
let intentModalMode = null; // 'add' | 'collapse'
let intentModalInsertIndex = null;
let intentModalCollapseRange = null;
let assertionModalTargetIndex = null;
let recordingPollInterval = null;

// ─── DOM References ───

const btnToggle = document.getElementById('btn-toggle-recording');
const recordingStatus = document.getElementById('recording-status');
const btnClearAll = document.getElementById('btn-clear-all');
const btnAddIntent = document.getElementById('btn-add-intent');
const actionList = document.getElementById('action-list');
const emptyLogMsg = document.getElementById('empty-log-msg');
const btnExport = document.getElementById('btn-export');
const btnExportZip = document.getElementById('btn-export-zip');
const exportOutputWrapper = document.getElementById('export-output-wrapper');
const exportOutput = document.getElementById('export-output');
const btnCopy = document.getElementById('btn-copy');
const copyConfirmation = document.getElementById('copy-confirmation');
const zipStatus = document.getElementById('zip-status');
const btnRun = document.getElementById('btn-run');
const replaySummary = document.getElementById('replay-summary');
const sessionList = document.getElementById('session-list');
const emptySessionsMsg = document.getElementById('empty-sessions-msg');

// ─── Modal DOM References ───

const intentModal = document.getElementById('intent-modal');
const intentModalTitle = document.getElementById('intent-modal-title');
const intentTextInput = document.getElementById('intent-text-input');
const btnIntentCancel = document.getElementById('btn-intent-cancel');
const btnIntentConfirm = document.getElementById('btn-intent-confirm');

const assertionModal = document.getElementById('assertion-modal');
const assertionTextInput = document.getElementById('assertion-text-input');
const btnAssertionCancel = document.getElementById('btn-assertion-cancel');
const btnAssertionConfirm = document.getElementById('btn-assertion-confirm');

// ─── Helpers ───

/**
 * Sends a message to the background service worker and returns the response.
 * @param {object} message
 * @returns {Promise<any>}
 */
async function sendMessage(message) {
  return chrome.runtime.sendMessage(message);
}

/**
 * Returns the icon for a given action type.
 * @param {ActionEntry} action
 * @returns {string}
 */
/** Inline SVG icon templates (16x16, stroke-based, using currentColor). */
const SVG_ICONS = {
  click: `<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M3 1.5L3 10.5L5.5 8.5L7.5 12.5L9 12L7 7.5L11 7.5Z" fill="currentColor" stroke="none"/><path d="M11 4.5C12.5 6 12.5 8.5 11 10"/><path d="M13 3C14.8 5.5 14.8 9.5 13 12"/></svg>`,
  type: `<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><line x1="6" y1="2.5" x2="10" y2="2.5"/><line x1="8" y1="2.5" x2="8" y2="13.5"/><line x1="6" y1="13.5" x2="10" y2="13.5"/></svg>`,
  scroll: `<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><line x1="8" y1="1.5" x2="8" y2="14.5"/><path d="M5 4.5L8 1.5L11 4.5" stroke-linejoin="round"/><path d="M5 11.5L8 14.5L11 11.5" stroke-linejoin="round"/></svg>`,
  navigation: `<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="8" cy="8" r="6"/><line x1="2" y1="8" x2="14" y2="8"/><path d="M8 2C6 4 5.5 6 5.5 8C5.5 10 6 12 8 14"/><path d="M8 2C10 4 10.5 6 10.5 8C10.5 10 10 12 8 14"/></svg>`,
  intent: `<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M8 1.5L14.5 8L8 14.5L1.5 8Z" stroke-linejoin="round"/><circle cx="8" cy="8" r="1.5" fill="currentColor" stroke="none"/></svg>`,
  extract_variable: `<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><line x1="8" y1="8.5" x2="8" y2="1.5"/><path d="M5.5 4L8 1.5L10.5 4" stroke-linejoin="round"/><path d="M5 6.5L3 6.5L3 13.5L13 13.5L13 6.5L11 6.5"/></svg>`,
  action: `<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M10 1.5L5 9L8.5 9L6.5 14.5L12 7L8.5 7Z" fill="currentColor" stroke="none"/></svg>`,
  remove: `<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M1 5h14M13 5l-1 10H4L3 5M5 5V2h6v3" stroke-linejoin="round"/></svg>`,
  add: `<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><line x1="8" y1="3" x2="8" y2="13"/><line x1="3" y1="8" x2="13" y2="8"/></svg>`,
  save: `<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><line x1="8" y1="2" x2="8" y2="11"/><path d="M5 8.5L8 11.5L11 8.5" stroke-linejoin="round"/><line x1="3" y1="13.5" x2="13" y2="13.5"/></svg>`,
  stop: `<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" stroke="none"><rect x="3" y="3" width="10" height="10" rx="1.5"/></svg>`,
  play: `<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" stroke="none"><path d="M4.5 2.5L13 8L4.5 13.5Z"/></svg>`,
  check: `<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8.5L6.5 12L13 4"/></svg>`,
  fail: `<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="4" y1="4" x2="12" y2="12"/><line x1="12" y1="4" x2="4" y2="12"/></svg>`,
  package: `<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 5L8 2L14 5L8 8Z"/><path d="M2 5V11L8 14V8"/><path d="M14 5V11L8 14"/></svg>`,
  hourglass: `<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 2h8M4 14h8M5 2v2c0 2 3 3 3 4s-3 2-3 4v2M11 2v2c0 2-3 3-3 4s3 2 3 4v2"/></svg>`,
};

// Inject toolbar button icons
document.getElementById('btn-save-icon').innerHTML = SVG_ICONS.save;
document.getElementById('btn-add-icon').innerHTML = SVG_ICONS.add;
document.getElementById('btn-clear-icon').innerHTML = SVG_ICONS.remove;

/**
 * Returns an inline SVG icon string for the given action.
 * @param {ActionEntry} action
 * @returns {string}
 */
function getActionIcon(action) {
  if (action.isIntent) return SVG_ICONS.intent;
  switch (action.type) {
    case 'click': return SVG_ICONS.click;
    case 'type': return SVG_ICONS.type;
    case 'scroll': return SVG_ICONS.scroll;
    case 'navigation': return SVG_ICONS.navigation;
    case 'tab_switch': return SVG_ICONS.navigation;
    case 'extract_variable': return SVG_ICONS.extract_variable;
    case 'paste': return SVG_ICONS.type;
    case 'change': return SVG_ICONS.action;
    default: return SVG_ICONS.action;
  }
}

/**
 * Returns the CSS class modifier for visual distinction.
 * @param {ActionEntry} action
 * @returns {string}
 */
function getActionClass(action) {
  if (action.isIntent) return 'intent';
  if (action.type === 'extract_variable') return 'extract-variable';
  if (action.type === 'paste') return 'paste';
  if (action.type === 'tab_switch') return 'tab-switch';
  return '';
}

// ─── Tab Navigation ───

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    // Deactivate all tabs
    document.querySelectorAll('.tab-btn').forEach(b => {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));

    // Activate clicked tab
    btn.classList.add('active');
    btn.setAttribute('aria-selected', 'true');
    const panel = document.getElementById(btn.dataset.tab);
    if (panel) panel.classList.add('active');

    // Check screenshot availability when switching to export tab
    if (btn.dataset.tab === 'tab-export') {
      updateZipButtonState();
    }
  });
});

// ─── Task 6.2: Start/Stop Recording ───

btnToggle?.addEventListener('click', async () => {
  if (isRecording) {
    await sendMessage({ kind: 'STOP_RECORDING' });
    setRecordingState(false);
  } else {
    // Get the active tab to start recording on it
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab) {
      await sendMessage({ kind: 'START_RECORDING', tabId: tab.id, url: tab.url });
      setRecordingState(true);
    }
  }
  // Refresh state
  await loadState();
});

/**
 * Updates the UI to reflect recording state.
 * @param {boolean} recording
 */
function setRecordingState(recording) {
  isRecording = recording;
  if (recording) {
    btnToggle.classList.add('recording');
    btnToggle.querySelector('.btn-icon').innerHTML = SVG_ICONS.stop;
    btnToggle.querySelector('.btn-label').textContent = 'Stop Recording';
    btnToggle.setAttribute('aria-label', 'Stop Recording');
    recordingStatus.classList.remove('hidden');
    // Set red badge on extension icon
    chrome.action.setBadgeText({ text: 'REC' });
    chrome.action.setBadgeBackgroundColor({ color: '#e74c3c' });
    // Poll for new actions while recording
    if (!recordingPollInterval) {
      recordingPollInterval = setInterval(async () => {
        // Don't refresh while user is editing a prompt
        if (document.querySelector('.action-prompt.editing') || document.querySelector('.assertion-text.editing')) {
          return;
        }
        try {
          const state = await sendMessage({ kind: 'GET_STATE' });
          if (state && state.actions && state.actions.length !== currentActions.length) {
            renderActionLog(state.actions);
          }
          if (!state || !state.isRecording) {
            clearInterval(recordingPollInterval);
            recordingPollInterval = null;
            setRecordingState(false);
            await loadState();
          }
        } catch { /* ignore */ }
      }, 500);
    }
  } else {
    btnToggle.classList.remove('recording');
    btnToggle.querySelector('.btn-icon').innerHTML = SVG_ICONS.play;
    btnToggle.querySelector('.btn-label').textContent = 'Start Recording';
    btnToggle.setAttribute('aria-label', 'Start Recording');
    recordingStatus.classList.add('hidden');
    // Clear badge
    chrome.action.setBadgeText({ text: '' });
    // Stop polling
    if (recordingPollInterval) {
      clearInterval(recordingPollInterval);
      recordingPollInterval = null;
    }
  }
}

// ─── Task 6.3: Action Log Rendering ───

/**
 * Renders the full action log list.
 * @param {ActionEntry[]} actions
 */
function renderActionLog(actions) {
  currentActions = actions;
  actionList.innerHTML = '';

  if (!actions || actions.length === 0) {
    emptyLogMsg.classList.remove('hidden');
    btnClearAll.classList.add('hidden');
    return;
  }

  emptyLogMsg.classList.add('hidden');
  btnClearAll.classList.remove('hidden');

  actions.forEach((action, index) => {
    const li = createActionEntry(action, index);
    actionList.appendChild(li);
  });

  // Auto-scroll to show the latest action
  if (actionList.lastElementChild) {
    actionList.lastElementChild.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

/**
 * Creates a single action entry DOM element.
 * @param {ActionEntry} action
 * @param {number} index
 * @returns {HTMLLIElement}
 */
function createActionEntry(action, index) {
  const li = document.createElement('li');
  li.className = `action-entry ${getActionClass(action)}`;
  li.dataset.index = index;

  // Drag attributes (Task 6.5)
  li.draggable = true;
  li.addEventListener('dragstart', handleDragStart);
  li.addEventListener('dragover', handleDragOver);
  li.addEventListener('dragenter', handleDragEnter);
  li.addEventListener('dragleave', handleDragLeave);
  li.addEventListener('drop', handleDrop);
  li.addEventListener('dragend', handleDragEnd);

  // Icon
  const icon = document.createElement('span');
  icon.className = 'action-icon';
  icon.innerHTML = getActionIcon(action);
  icon.setAttribute('aria-hidden', 'true');
  li.appendChild(icon);

  // Content
  const content = document.createElement('div');
  content.className = 'action-content';

  // Index + prompt
  const promptRow = document.createElement('div');

  const indexSpan = document.createElement('span');
  indexSpan.className = 'action-index';
  indexSpan.textContent = `${index + 1}.`;
  promptRow.appendChild(indexSpan);

  // Prompt text (Task 6.4: click-to-edit)
  const promptSpan = document.createElement('span');
  promptSpan.className = 'action-prompt';
  promptSpan.textContent = action.prompt;
  promptSpan.setAttribute('role', 'textbox');
  promptSpan.setAttribute('tabindex', '0');
  promptSpan.addEventListener('click', () => startInlineEdit(promptSpan, index));
  promptSpan.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === 'F2') {
      e.preventDefault();
      startInlineEdit(promptSpan, index);
    }
  });
  promptRow.appendChild(promptSpan);

  // Variable name badge for extract_variable actions
  if (action.type === 'extract_variable' && action.variableName) {
    const varBadge = document.createElement('span');
    varBadge.className = 'variable-badge';
    varBadge.textContent = action.variableName;
    promptRow.appendChild(varBadge);
  }

  // Source variable badge for paste actions
  if (action.type === 'paste' && action.sourceVariableName) {
    const varBadge = document.createElement('span');
    varBadge.className = 'variable-badge';
    varBadge.textContent = `← ${action.sourceVariableName}`;
    promptRow.appendChild(varBadge);
  }

  // Collapsed count indicator (Task 8.5)
  if (action.isIntent && action.collapsedActions && action.collapsedActions.length > 0) {
    const countSpan = document.createElement('span');
    countSpan.className = 'collapsed-count';
    countSpan.textContent = `(${action.collapsedActions.length} collapsed)`;
    promptRow.appendChild(countSpan);
  }

  content.appendChild(promptRow);

  // Assertions (Task 6.7 + Task 9.3: inline edit/delete)
  if (action.assertions && action.assertions.length > 0) {
    const assertionsList = document.createElement('div');
    assertionsList.className = 'assertion-list';
    action.assertions.forEach((assertion, aIdx) => {
      const item = document.createElement('div');
      let resultClass = '';
      if (assertion.result) {
        resultClass = assertion.result.passed ? 'assertion-result-pass' : 'assertion-result-fail';
      }
      item.className = `assertion-item ${resultClass}`;

      const aIcon = document.createElement('span');
      aIcon.className = 'assertion-icon';
      aIcon.innerHTML = assertion.result
        ? (assertion.result.passed ? SVG_ICONS.check : SVG_ICONS.fail)
        : SVG_ICONS.check;
      item.appendChild(aIcon);

      const aText = document.createElement('span');
      aText.className = 'assertion-text';
      aText.textContent = assertion.text;
      item.appendChild(aText);

      // Task 9.3: Inline edit and delete controls
      const aControls = document.createElement('div');
      aControls.className = 'assertion-controls';

      const btnEditAssertion = document.createElement('button');
      btnEditAssertion.className = 'btn-icon-only';
      btnEditAssertion.textContent = '✎';
      btnEditAssertion.title = 'Edit assertion';
      btnEditAssertion.addEventListener('click', (e) => {
        e.stopPropagation();
        startAssertionInlineEdit(aText, index, aIdx);
      });
      aControls.appendChild(btnEditAssertion);

      const btnDelAssertion = document.createElement('button');
      btnDelAssertion.className = 'btn-icon-only btn-delete';
      btnDelAssertion.innerHTML = SVG_ICONS.remove;
      btnDelAssertion.title = 'Delete assertion';
      btnDelAssertion.addEventListener('click', (e) => {
        e.stopPropagation();
        deleteAssertionAction(index, aIdx);
      });
      aControls.appendChild(btnDelAssertion);

      item.appendChild(aControls);
      assertionsList.appendChild(item);
    });
    content.appendChild(assertionsList);
  }

  li.appendChild(content);

  // Controls (Task 6.6: delete button + Task 7/8/9 action menu)
  const controls = document.createElement('div');
  controls.className = 'action-controls';

  // Action menu buttons
  const menu = document.createElement('div');
  menu.className = 'action-menu';

  controls.appendChild(menu);

  // Expand button for collapsed intents
  if (action.isIntent && action.collapsedActions && action.collapsedActions.length > 0) {
    const btnExpand = document.createElement('button');
    btnExpand.className = 'btn-small btn-expand';
    btnExpand.textContent = '↕ Expand';
    btnExpand.title = `Expand ${action.collapsedActions.length} collapsed actions`;
    btnExpand.addEventListener('click', (e) => {
      e.stopPropagation();
      expandIntent(index);
    });
    controls.appendChild(btnExpand);
  }

  const btnDelete = document.createElement('button');
  btnDelete.className = 'btn-icon-only btn-delete';
  btnDelete.innerHTML = SVG_ICONS.remove;
  btnDelete.title = 'Delete action';
  btnDelete.setAttribute('aria-label', `Delete action ${index + 1}`);
  btnDelete.addEventListener('click', (e) => {
    e.stopPropagation();
    deleteAction(index);
  });
  controls.appendChild(btnDelete);

  li.appendChild(controls);

  return li;
}

// ─── Task 6.4: Inline Prompt Editing ───

/**
 * Starts inline editing on a prompt span.
 * @param {HTMLSpanElement} promptSpan
 * @param {number} index
 */
function startInlineEdit(promptSpan, index) {
  if (promptSpan.contentEditable === 'true') return;

  const originalText = promptSpan.textContent;
  promptSpan.contentEditable = 'true';
  promptSpan.classList.add('editing');
  promptSpan.focus();

  // Select all text
  const range = document.createRange();
  range.selectNodeContents(promptSpan);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);

  const finishEdit = async () => {
    promptSpan.contentEditable = 'false';
    promptSpan.classList.remove('editing');
    const newText = promptSpan.textContent.trim();
    if (newText && newText !== originalText) {
      await sendMessage({ kind: 'UPDATE_PROMPT', index, newPrompt: newText });
      await loadState();
    } else {
      promptSpan.textContent = originalText;
    }
  };

  promptSpan.addEventListener('blur', finishEdit, { once: true });
  promptSpan.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      promptSpan.blur();
    }
    if (e.key === 'Escape') {
      promptSpan.textContent = originalText;
      promptSpan.blur();
    }
  });
}

// ─── Task 6.5: Drag-to-Reorder ───

function handleDragStart(e) {
  dragSourceIndex = parseInt(e.currentTarget.dataset.index, 10);
  e.currentTarget.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/plain', dragSourceIndex.toString());
}

function handleDragOver(e) {
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
}

function handleDragEnter(e) {
  e.preventDefault();
  e.currentTarget.classList.add('drag-over');
}

function handleDragLeave(e) {
  e.currentTarget.classList.remove('drag-over');
}

async function handleDrop(e) {
  e.preventDefault();
  e.currentTarget.classList.remove('drag-over');
  const toIndex = parseInt(e.currentTarget.dataset.index, 10);
  if (dragSourceIndex !== null && dragSourceIndex !== toIndex) {
    await sendMessage({ kind: 'REORDER_ACTION', fromIndex: dragSourceIndex, toIndex });
    await loadState();
  }
}

function handleDragEnd(e) {
  e.currentTarget.classList.remove('dragging');
  document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
  dragSourceIndex = null;
}

// ─── Task 6.6: Delete Action and Clear All ───

/**
 * Deletes a single action by index.
 * @param {number} index
 */
async function deleteAction(index) {
  await sendMessage({ kind: 'DELETE_ACTION', index });
  await loadState();
}

const btnSaveSession = document.getElementById('btn-save-session');

btnSaveSession?.addEventListener('click', async () => {
  if (currentActions.length === 0) return;
  const name = prompt('Session name:', `Recording ${new Date().toLocaleString()}`);
  if (!name) return;

  // Check if a session with this name already exists
  const listResult = await sendMessage({ kind: 'LIST_SESSIONS' });
  if (listResult && listResult.success && listResult.sessions) {
    const existing = listResult.sessions.find(s => s.name === name);
    if (existing) {
      if (!confirm(`A session named "${name}" already exists. Overwrite it?`)) return;
      // Delete the old one first
      await sendMessage({ kind: 'DELETE_SESSION', sessionId: existing.id });
    }
  }

  const result = await sendMessage({ kind: 'SAVE_SESSION', sessionName: name });
  if (result && result.success) {
    btnSaveSession.innerHTML = `<span class="btn-svg">${SVG_ICONS.check}</span>Saved`;
    setTimeout(() => { btnSaveSession.innerHTML = `<span class="btn-svg">${SVG_ICONS.save}</span>Save`; }, 2000);
    await loadSessions();
  }
});

btnClearAll?.addEventListener('click', async () => {
  if (currentActions.length === 0) return;
  if (!confirm('Clear all recorded actions? This cannot be undone.')) return;
  await sendMessage({ kind: 'CLEAR_ALL' });
  await loadState();
});

// ─── Task 8.4: Intent Prompt Modal ───

btnAddIntent?.addEventListener('click', () => {
  intentModalMode = 'add';
  intentModalInsertIndex = currentActions.length; // Insert at end by default
  intentModalTitle.textContent = 'Add Intent Prompt';
  intentTextInput.value = '';
  btnIntentConfirm.textContent = 'Add';
  intentModal.classList.remove('hidden');
  intentTextInput.focus();
});

btnIntentCancel?.addEventListener('click', () => {
  intentModal.classList.add('hidden');
  intentModalMode = null;
});

btnIntentConfirm?.addEventListener('click', async () => {
  const text = intentTextInput.value.trim();
  if (!text) return;

  if (intentModalMode === 'add') {
    await sendMessage({ kind: 'ADD_INTENT_PROMPT', atIndex: intentModalInsertIndex, intentText: text });
  } else if (intentModalMode === 'collapse' && intentModalCollapseRange) {
    await sendMessage({
      kind: 'COLLAPSE_TO_INTENT',
      startIndex: intentModalCollapseRange.start,
      endIndex: intentModalCollapseRange.end,
      intentText: text,
    });
  }

  intentModal.classList.add('hidden');
  intentModalMode = null;
  intentModalCollapseRange = null;
  await loadState();
});

// ─── Task 8.5: Expand Intent ───

/**
 * Expands a collapsed intent back to its original actions.
 * @param {number} index
 */
async function expandIntent(index) {
  await sendMessage({ kind: 'EXPAND_INTENT', index });
  await loadState();
}

// ─── Task 9.2/9.3: Assertion Modal ───

btnAssertionCancel?.addEventListener('click', () => {
  assertionModal.classList.add('hidden');
  assertionModalTargetIndex = null;
});

btnAssertionConfirm?.addEventListener('click', async () => {
  const text = assertionTextInput.value.trim();
  if (!text) return;

  const assertion = {
    id: Date.now().toString(36) + Math.random().toString(36).slice(2, 8),
    text,
  };

  await sendMessage({ kind: 'ADD_ASSERTION', actionIndex: assertionModalTargetIndex, assertion });
  assertionModal.classList.add('hidden');
  assertionModalTargetIndex = null;
  await loadState();
});

/**
 * Starts inline editing of an assertion text.
 * @param {HTMLSpanElement} textSpan
 * @param {number} actionIndex
 * @param {number} assertionIndex
 */
function startAssertionInlineEdit(textSpan, actionIndex, assertionIndex) {
  if (textSpan.contentEditable === 'true') return;

  const originalText = textSpan.textContent;
  textSpan.contentEditable = 'true';
  textSpan.classList.add('editing');
  textSpan.focus();

  const range = document.createRange();
  range.selectNodeContents(textSpan);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);

  const finishEdit = async () => {
    textSpan.contentEditable = 'false';
    textSpan.classList.remove('editing');
    const newText = textSpan.textContent.trim();
    if (newText && newText !== originalText) {
      await sendMessage({ kind: 'UPDATE_ASSERTION', actionIndex, assertionIndex, text: newText });
      await loadState();
    } else {
      textSpan.textContent = originalText;
    }
  };

  textSpan.addEventListener('blur', finishEdit, { once: true });
  textSpan.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      textSpan.blur();
    }
    if (e.key === 'Escape') {
      textSpan.textContent = originalText;
      textSpan.blur();
    }
  });
}

/**
 * Deletes an assertion from an action.
 * @param {number} actionIndex
 * @param {number} assertionIndex
 */
async function deleteAssertionAction(actionIndex, assertionIndex) {
  await sendMessage({ kind: 'DELETE_ASSERTION', actionIndex, assertionIndex });
  await loadState();
}

// ─── Export Panel ───

btnExport?.addEventListener('click', async () => {
  const response = await sendMessage({ kind: 'EXPORT_SCRIPT' });
  if (response && response.script) {
    exportOutput.value = response.script;
    exportOutputWrapper.classList.remove('hidden');
  }
});

btnCopy?.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(exportOutput.value);
    copyConfirmation.classList.remove('hidden');
    setTimeout(() => copyConfirmation.classList.add('hidden'), 2000);
  } catch {
    // Fallback: select all text for manual copy
    exportOutput.select();
    exportOutput.setSelectionRange(0, exportOutput.value.length);
  }
});

// ─── ZIP Export ───

/**
 * Checks if screenshots are available in memory and updates the ZIP button state.
 */
async function updateZipButtonState() {
  if (!btnExportZip) return;

  if (currentActions.length === 0) {
    btnExportZip.disabled = true;
    btnExportZip.title = 'No actions to export';
    zipStatus.classList.add('hidden');
    return;
  }

  try {
    const response = await sendMessage({ kind: 'GET_SCREENSHOTS' });
    const screenshots = (response && response.screenshots) || {};
    const count = Object.keys(screenshots).length;

    if (count === 0) {
      btnExportZip.disabled = true;
      btnExportZip.title = 'No screenshots available';
      zipStatus.textContent = 'No screenshots available. To save storage space, screenshots are not persisted with sessions — re-record to capture them.';
      zipStatus.classList.remove('hidden');
      zipStatus.classList.add('error');
    } else {
      btnExportZip.disabled = false;
      btnExportZip.title = `Export ZIP with ${count} screenshot${count !== 1 ? 's' : ''}`;
      zipStatus.classList.add('hidden');
      zipStatus.classList.remove('error');
    }
  } catch {
    btnExportZip.disabled = true;
    btnExportZip.title = 'Unable to check screenshots';
  }
}

btnExportZip?.addEventListener('click', async () => {
  btnExportZip.disabled = true;
  btnExportZip.textContent = 'Building ZIP...';
  zipStatus.classList.add('hidden');
  zipStatus.classList.remove('error');

  try {
    // Get the script
    const scriptResponse = await sendMessage({ kind: 'EXPORT_SCRIPT' });
    if (!scriptResponse || !scriptResponse.script) {
      throw new Error('No script to export');
    }

    // Get screenshots
    const screenshotResponse = await sendMessage({ kind: 'GET_SCREENSHOTS' });
    const screenshots = (screenshotResponse && screenshotResponse.screenshots) || {};

    // Build ZIP
    const zip = new JSZip();
    zip.file('test_script.py', scriptResponse.script);

    // Add screenshots, named by action index for easy correlation
    const actions = currentActions;
    let screenshotCount = 0;
    const imgFolder = zip.folder('screenshots');
    for (let i = 0; i < actions.length; i++) {
      const dataUrl = screenshots[actions[i].id];
      if (dataUrl) {
        // Convert data URL to binary
        const base64 = dataUrl.split(',')[1];
        const paddedIndex = String(i + 1).padStart(3, '0');
        const safePrompt = (actions[i].prompt || 'action')
          .slice(0, 40)
          .replace(/[^a-zA-Z0-9_-]/g, '_');
        imgFolder.file(`${paddedIndex}_${safePrompt}.jpg`, base64, { base64: true });
        screenshotCount++;
      }
    }

    const blob = await zip.generateAsync({ type: 'blob' });

    // Trigger download
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const now = new Date();
    const date = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    const time = `${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}${String(now.getSeconds()).padStart(2, '0')}`;
    const filename = `nova-act-recording-${date}-${time}.zip`;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    zipStatus.innerHTML = `<span class="btn-svg" style="display:inline-flex;vertical-align:middle;margin-right:4px">${SVG_ICONS.check}</span>${filename} — ${screenshotCount} screenshot${screenshotCount !== 1 ? 's' : ''}`;
    zipStatus.classList.remove('hidden', 'error');
  } catch (e) {
    zipStatus.textContent = `Export failed: ${e.message}`;
    zipStatus.classList.remove('hidden');
    zipStatus.classList.add('error');
  }

  btnExportZip.disabled = false;
  btnExportZip.textContent = 'Export ZIP';
});

// ─── Replay Panel ───

const chkNewPlayground = document.getElementById('chk-new-playground');

btnRun?.addEventListener('click', async () => {
  btnRun.disabled = true;
  btnRun.textContent = 'Opening Playground...';
  replaySummary.classList.add('hidden');

  const forceNew = chkNewPlayground.checked;
  const result = await sendMessage({ kind: 'RUN_ON_PLAYGROUND', forceNewTab: forceNew });

  if (result && result.success) {
    replaySummary.innerHTML = `<span class="btn-svg" style="display:inline-flex;vertical-align:middle;margin-right:4px">${SVG_ICONS.check}</span>Playground opened. Script will be injected into the editor.`;
  } else {
    replaySummary.textContent = (result && result.error) || 'Failed to open playground';
  }
  replaySummary.classList.remove('hidden');

  btnRun.disabled = false;
  btnRun.textContent = 'Run on Playground';
});


// ─── State Loading ───

/**
 * Loads the current state from the background service worker.
 */
async function loadState() {
  try {
    const state = await sendMessage({ kind: 'GET_STATE' });
    if (state) {
      setRecordingState(state.isRecording);
      renderActionLog(state.actions || []);
      updateZipButtonState();
    }
  } catch {
    // Background may not be ready yet
  }
}

/**
 * Loads saved sessions from storage via background message.
 */
async function loadSessions() {
  try {
    const result = await sendMessage({ kind: 'LIST_SESSIONS' });
    if (result && result.success) {
      renderSessionList(result.sessions || []);
    } else {
      // Fallback to direct storage read
      const storageResult = await chrome.storage.local.get('sessions');
      renderSessionList(storageResult.sessions || []);
    }
  } catch {
    // Ignore storage errors
  }
}

/**
 * Renders the session history list.
 * @param {SessionSummary[]} sessions
 */
function renderSessionList(sessions) {
  sessionList.innerHTML = '';

  if (!sessions || sessions.length === 0) {
    emptySessionsMsg.classList.remove('hidden');
    return;
  }

  emptySessionsMsg.classList.add('hidden');

  sessions.forEach(session => {
    const li = document.createElement('li');
    li.className = 'session-item';

    const info = document.createElement('div');
    info.className = 'session-info';

    if (session.name) {
      const nameEl = document.createElement('div');
      nameEl.className = 'session-name';
      nameEl.textContent = session.name;
      nameEl.style.cssText = 'font-weight: 600; font-size: 13px; margin-bottom: 2px;';
      info.appendChild(nameEl);
    }

    const url = document.createElement('div');
    url.className = 'session-url';
    url.textContent = session.startingUrl || 'Unknown URL';
    url.title = session.startingUrl;
    info.appendChild(url);

    const meta = document.createElement('div');
    meta.className = 'session-meta';
    const date = new Date(session.startedAt).toLocaleString();
    meta.textContent = `${date} · ${session.actionCount} actions`;
    info.appendChild(meta);

    li.appendChild(info);

    const actions = document.createElement('div');
    actions.className = 'session-actions';

    const btnLoad = document.createElement('button');
    btnLoad.className = 'btn-small';
    btnLoad.textContent = 'Load';
    btnLoad.addEventListener('click', async () => {
      await sendMessage({ kind: 'LOAD_SESSION', sessionId: session.id });
      await loadState();
      // Switch to actions tab
      document.querySelector('[data-tab="tab-actions"]').click();
    });
    actions.appendChild(btnLoad);

    const btnDel = document.createElement('button');
    btnDel.className = 'btn-small btn-danger';
    btnDel.textContent = 'Delete';
    btnDel.addEventListener('click', async () => {
      await sendMessage({ kind: 'DELETE_SESSION', sessionId: session.id });
      await loadSessions();
    });
    actions.appendChild(btnDel);

    li.appendChild(actions);
    sessionList.appendChild(li);
  });
}

// ─── Initialize ───

document.addEventListener('DOMContentLoaded', async () => {
  await loadState();
  await loadSessions();
});
