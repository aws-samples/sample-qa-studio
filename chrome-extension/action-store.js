// Nova Act Recorder - Action Store
// Holds the ordered action log and provides CRUD operations.

'use strict';

import { generateId } from './session-manager.js';
import { PromptGenerator } from './prompt-generator.js';

/**
 * @typedef {import('./types.js').RawAction} RawAction
 * @typedef {import('./types.js').ActionEntry} ActionEntry
 */

/** Shared PromptGenerator instance used by ActionStore. */
const _promptGenerator = new PromptGenerator();

/**
 * Generates a placeholder prompt for a raw action.
 * Delegates to PromptGenerator.generatePrompt().
 * @param {RawAction} rawAction
 * @returns {string}
 */
export function generatePlaceholderPrompt(rawAction) {
  // Build a minimal ActionEntry-like object for the PromptGenerator
  /** @type {import('./types.js').ActionEntry} */
  const entry = {
    id: '',
    type: rawAction.type,
    rawAction,
    prompt: '',
    promptEdited: false,
    url: rawAction.url,
    timestamp: rawAction.timestamp,
    isIntent: false,
    assertions: [],
  };
  return _promptGenerator.generatePrompt(entry);
}

/**
 * Determines if a scroll action should be consolidated with the previous action.
 * Consecutive same-direction scrolls (with same container) are merged.
 * @param {ActionEntry[]} actions
 * @param {RawAction} newAction
 * @returns {boolean}
 */
export function shouldConsolidateScroll(actions, newAction) {
  if (newAction.type !== 'scroll' || actions.length === 0) return false;
  const last = actions[actions.length - 1];
  if (last.type !== 'scroll') return false;

  // Same direction check
  const lastDir = last.rawAction ? last.rawAction.value : null;
  if (lastDir !== newAction.value) return false;

  // Same container check
  const lastContainer = last.rawAction ? last.rawAction.scrollContainer : undefined;
  const newContainer = newAction.scrollContainer;
  if (!lastContainer && !newContainer) return true;
  if (!lastContainer || !newContainer) return false;
  return lastContainer.text === newContainer.text && lastContainer.tagName === newContainer.tagName;
}

/**
 * ActionStore manages the ordered action log with CRUD operations.
 */
export class ActionStore {
  constructor() {
    /** @type {ActionEntry[]} */
    this._actions = [];
    /** @type {number} */
    this._variableCounter = 0;
    /** @type {number|undefined} */
    this._startingTabId = undefined;
  }

  /**
   * Sets the starting tab ID for multi-tab export.
   * Persisted separately from the session so it survives session stop.
   * @param {number|undefined} tabId
   */
  setStartingTabId(tabId) {
    this._startingTabId = tabId;
  }

  /**
   * Returns the starting tab ID.
   * @returns {number|undefined}
   */
  getStartingTabId() {
    return this._startingTabId;
  }

  /**
   * Creates an ActionEntry from a RawAction, generates a prompt, and adds to the log.
   * Handles scroll consolidation: consecutive same-direction scrolls are merged.
   * @param {RawAction} rawAction
   * @returns {ActionEntry} The added (or consolidated) action entry
   */
  addAction(rawAction) {
    // Scroll consolidation
    if (shouldConsolidateScroll(this._actions, rawAction)) {
      // Update the timestamp of the existing scroll action to the latest
      const existing = this._actions[this._actions.length - 1];
      existing.timestamp = rawAction.timestamp;
      if (existing.rawAction) {
        existing.rawAction.timestamp = rawAction.timestamp;
      }
      return existing;
    }

    // Suppress duplicate type after paste on the same element.
    // The content script's paste handler tries to update the baseline value,
    // but a race condition can still produce a redundant type action with the
    // literal pasted text. Drop it here so the export only contains the
    // variable-reference f-string, not the literal duplicate.
    if (rawAction.type === 'type' && this._actions.length > 0) {
      const prev = this._actions[this._actions.length - 1];
      if (prev.type === 'paste' && prev.rawAction) {
        const sameElement = rawAction.element && prev.rawAction.element
          && rawAction.element.text === prev.rawAction.element.text;
        if (sameElement) {
          return prev;
        }
      }
    }

    const prompt = generatePlaceholderPrompt(rawAction);

    /** @type {ActionEntry} */
    const entry = {
      id: generateId(),
      type: rawAction.type,
      rawAction,
      prompt,
      promptEdited: false,
      url: rawAction.url,
      timestamp: rawAction.timestamp,
      isIntent: false,
      assertions: [],
    };

    if (rawAction.type === 'extract_variable') {
      this._variableCounter++;
      entry.variableName = `var_${this._variableCounter}`;
      entry.selectedText = rawAction.selectedText || '';
    }

    if (rawAction.type === 'paste') {
      // Walk backward to find the last extract_variable and link to it
      for (let i = this._actions.length - 1; i >= 0; i--) {
        if (this._actions[i].type === 'extract_variable' && this._actions[i].variableName) {
          entry.sourceVariableName = this._actions[i].variableName;
          break;
        }
      }
    }

    this._actions.push(entry);
    return entry;
  }

  /**
   * Returns the ordered array of action entries.
   * @returns {ActionEntry[]}
   */
  getActions() {
    return [...this._actions];
  }

  /**
   * Returns the internal actions array reference (for session sync).
   * @returns {ActionEntry[]}
   */
  getActionsRef() {
    return this._actions;
  }

  /**
   * Moves an action from one index to another.
   * @param {number} fromIndex
   * @param {number} toIndex
   */
  reorderAction(fromIndex, toIndex) {
    if (fromIndex < 0 || fromIndex >= this._actions.length) return;
    if (toIndex < 0 || toIndex >= this._actions.length) return;
    if (fromIndex === toIndex) return;

    const [item] = this._actions.splice(fromIndex, 1);
    this._actions.splice(toIndex, 0, item);
  }

  /**
   * Removes an action at the given index.
   * @param {number} index
   */
  deleteAction(index) {
    if (index < 0 || index >= this._actions.length) return;
    this._actions.splice(index, 1);
  }

  /**
   * Updates the prompt text for an action at the given index.
   * Sets promptEdited to true.
   * @param {number} index
   * @param {string} newPrompt
   */
  updatePrompt(index, newPrompt) {
    if (index < 0 || index >= this._actions.length) return;
    this._actions[index].prompt = newPrompt;
    this._actions[index].promptEdited = true;
  }

  /**
   * Removes all actions from the log.
   */
  clearAll() {
    this._actions = [];
    this._variableCounter = 0;
    this._startingTabId = undefined;
  }

  /**
   * Sets the actions array directly (used for restoring state).
   * @param {ActionEntry[]} actions
   */
  setActions(actions) {
    this._actions = actions;
    // Recalculate variable counter from restored actions
    const maxVar = actions.reduce((max, a) => {
      if (a.type === 'extract_variable' && a.variableName) {
        const num = parseInt(a.variableName.replace('var_', ''), 10);
        return isNaN(num) ? max : Math.max(max, num);
      }
      return max;
    }, 0);
    this._variableCounter = maxVar;
  }

  /**
   * Inserts a free-text intent prompt at the given index.
   * @param {number} atIndex - Position to insert (0 to length inclusive)
   * @param {string} intentText
   * @returns {ActionEntry} The inserted intent entry
   */
  addIntentPrompt(atIndex, intentText) {
    const clampedIndex = Math.max(0, Math.min(atIndex, this._actions.length));

    /** @type {ActionEntry} */
    const entry = {
      id: generateId(),
      type: 'intent',
      prompt: intentText,
      promptEdited: false,
      url: '',
      timestamp: Date.now(),
      isIntent: true,
      assertions: [],
    };

    this._actions.splice(clampedIndex, 0, entry);
    return entry;
  }

  /**
   * Replaces a contiguous range of actions [startIndex, endIndex] with a single intent entry.
   * The original actions are stored in collapsedActions on the intent entry.
   * @param {number} startIndex
   * @param {number} endIndex
   * @param {string} intentText
   * @returns {ActionEntry|null} The collapsed intent entry, or null if indices are invalid
   */
  collapseToIntent(startIndex, endIndex, intentText) {
    if (startIndex < 0 || endIndex >= this._actions.length || startIndex > endIndex) return null;

    const collapsed = this._actions.splice(startIndex, endIndex - startIndex + 1);

    /** @type {ActionEntry} */
    const entry = {
      id: generateId(),
      type: 'intent',
      prompt: intentText,
      promptEdited: false,
      url: collapsed[0] ? collapsed[0].url : '',
      timestamp: Date.now(),
      isIntent: true,
      collapsedActions: collapsed,
      assertions: [],
    };

    this._actions.splice(startIndex, 0, entry);
    return entry;
  }

  /**
   * Expands a collapsed intent entry back into its original actions.
   * @param {number} index
   * @returns {boolean} true if expanded, false if not a collapsed intent
   */
  expandIntent(index) {
    if (index < 0 || index >= this._actions.length) return false;
    const entry = this._actions[index];
    if (!entry.isIntent || !entry.collapsedActions || entry.collapsedActions.length === 0) return false;

    const restored = entry.collapsedActions;
    this._actions.splice(index, 1, ...restored);
    return true;
  }

  /**
   * Adds an assertion to the action at the given index.
   * @param {number} actionIndex
   * @param {import('./types.js').Assertion} assertion
   */
  addAssertion(actionIndex, assertion) {
    if (actionIndex < 0 || actionIndex >= this._actions.length) return;
    if (!this._actions[actionIndex].assertions) {
      this._actions[actionIndex].assertions = [];
    }
    this._actions[actionIndex].assertions.push(assertion);
  }

  /**
   * Updates the text of an assertion at the given indices.
   * @param {number} actionIndex
   * @param {number} assertionIndex
   * @param {string} text
   */
  updateAssertion(actionIndex, assertionIndex, text) {
    if (actionIndex < 0 || actionIndex >= this._actions.length) return;
    const assertions = this._actions[actionIndex].assertions;
    if (!assertions || assertionIndex < 0 || assertionIndex >= assertions.length) return;
    assertions[assertionIndex].text = text;
  }

  /**
   * Deletes an assertion at the given indices.
   * @param {number} actionIndex
   * @param {number} assertionIndex
   */
  deleteAssertion(actionIndex, assertionIndex) {
    if (actionIndex < 0 || actionIndex >= this._actions.length) return;
    const assertions = this._actions[actionIndex].assertions;
    if (!assertions || assertionIndex < 0 || assertionIndex >= assertions.length) return;
    assertions.splice(assertionIndex, 1);
  }

  /**
   * Returns the number of actions in the log.
   * @returns {number}
   */
  get length() {
    return this._actions.length;
  }
}
