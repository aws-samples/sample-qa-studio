// Nova Act Recorder - Session Manager
// Manages recording lifecycle: start, stop, tab-scoping, and state recovery.

'use strict';

/**
 * Generates a simple UUID (v4-like).
 * Uses crypto.randomUUID() if available, otherwise falls back to a simple generator.
 * @returns {string}
 */
export function generateId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * @typedef {import('./types.js').RecordingSession} RecordingSession
 * @typedef {import('./types.js').RawAction} RawAction
 * @typedef {import('./types.js').ActionEntry} ActionEntry
 */

/**
 * SessionManager manages the recording lifecycle.
 * It tracks which tab is being recorded, whether recording is active,
 * and whether capture is paused due to tab switching.
 */
export class SessionManager {
  constructor() {
    /** @type {RecordingSession|null} */
    this._session = null;
    /** @type {boolean} */
    this._recording = false;
    /** @type {boolean} */
    this._paused = false;
  }

  /**
   * Starts a new recording session on the given tab.
   * Captures an initial navigation action for the tab's current URL.
   * @param {number} tabId
   * @param {string} [startingUrl=''] - The URL of the tab at recording start
   * @returns {RecordingSession}
   */
  startRecording(tabId, startingUrl = '') {
    this._session = {
      id: generateId(),
      startedAt: Date.now(),
      stoppedAt: undefined,
      tabId,
      startingTabId: tabId,  // Preserved separately — tabId gets mutated by handleTabActivated
      startingUrl,
      actions: [],
    };
    this._recording = true;
    this._paused = false;

    // Capture initial navigation action
    if (startingUrl) {
      /** @type {ActionEntry} */
      const navAction = {
        id: generateId(),
        type: 'navigation',
        rawAction: {
          type: 'navigation',
          timestamp: Date.now(),
          url: startingUrl,
          value: startingUrl,
        },
        prompt: `navigate to '${startingUrl}'`,
        promptEdited: false,
        url: startingUrl,
        timestamp: Date.now(),
        isIntent: false,
        assertions: [],
      };
      this._session.actions.push(navAction);
    }

    return this._session;
  }

  /**
   * Stops the current recording session and returns it.
   * @returns {RecordingSession|null}
   */
  stopRecording() {
    if (!this._session) return null;
    this._session.stoppedAt = Date.now();
    this._recording = false;
    this._paused = false;
    const session = this._session;
    this._session = null;
    return session;
  }

  /**
   * Returns whether a recording is currently active.
   * @returns {boolean}
   */
  isRecording() {
    return this._recording;
  }

  /**
   * Returns whether capture is currently paused (tab switched away).
   * @returns {boolean}
   */
  isPaused() {
    return this._paused;
  }

  /**
   * Returns the tab ID of the current recording, or null if not recording.
   * @returns {number|null}
   */
  getActiveTabId() {
    return this._session ? this._session.tabId : null;
  }

  /**
   * Returns the current session (for persistence or inspection).
   * @returns {RecordingSession|null}
   */
  getSession() {
    return this._session;
  }

  /**
   * Adds an action to the current session's action log.
   * @param {ActionEntry} actionEntry
   */
  addAction(actionEntry) {
    if (this._session) {
      this._session.actions.push(actionEntry);
    }
  }

  /**
   * Returns the actions from the current session.
   * @returns {ActionEntry[]}
   */
  getActions() {
    return this._session ? this._session.actions : [];
  }

  /**
   * Sets the actions array on the current session (used by ActionStore sync).
   * @param {ActionEntry[]} actions
   */
  setActions(actions) {
    if (this._session) {
      this._session.actions = actions;
    }
  }

  /**
   * Handles the recorded tab being closed.
   * Auto-stops the recording and preserves captured actions.
   * @param {number} tabId
   * @returns {RecordingSession|null} The stopped session if the closed tab was the recording tab
   */
  handleTabClosed(tabId) {
    if (this._recording && this._session && this._session.tabId === tabId) {
      return this.stopRecording();
    }
    return null;
  }

  /**
   * Handles tab activation changes.
   * Moves recording to the newly activated tab so that actions
   * continue to be captured across tab switches.
   * @param {number} activeTabId
   */
  handleTabActivated(activeTabId) {
    if (!this._recording || !this._session) return;

    this._session.tabId = activeTabId;
    this._paused = false;
  }

  /**
   * Returns whether an action from the given tab should be captured.
   * Actions are only captured from the recording tab and when not paused.
   * @param {number} tabId
   * @returns {boolean}
   */
  shouldCaptureAction(tabId) {
    if (!this._recording || !this._session) return false;
    if (this._paused) return false;
    return tabId === this._session.tabId;
  }

  /**
   * Restores session state from a persisted session object.
   * Used for service worker recovery.
   * @param {RecordingSession} session
   */
  restoreSession(session) {
    this._session = session;
    this._recording = true;
    this._paused = false;
  }
}
