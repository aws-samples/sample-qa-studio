// Nova Act Recorder - Storage Manager
// Handles session persistence via chrome.storage.local.

'use strict';

/**
 * @typedef {import('./types.js').RecordingSession} RecordingSession
 * @typedef {import('./types.js').SessionSummary} SessionSummary
 * @typedef {import('./types.js').StorageQuotaInfo} StorageQuotaInfo
 */

/** Default Chrome local storage quota in bytes (10MB). */
const STORAGE_QUOTA_BYTES = 10 * 1024 * 1024;

/** Warning threshold percentage for storage usage. */
export const STORAGE_WARNING_THRESHOLD = 90;

/**
 * StorageManager handles persistence of recording sessions
 * to chrome.storage.local. It maintains a sessions index for fast listing
 * and stores full session data under individual keys.
 *
 * Storage keys:
 *   - `sessions`       → SessionSummary[] (index of all saved sessions)
 *   - `session:{id}`   → RecordingSession  (full session data)
 */
export class StorageManager {
  /**
   * Creates a StorageManager.
   * @param {object} [storageBackend] - Optional storage backend (for testing). Must implement get/set/remove/getBytesInUse.
   */
  constructor(storageBackend) {
    this._storage = storageBackend || (typeof chrome !== 'undefined' && chrome.storage ? chrome.storage.local : null);
  }

  /**
   * Internal helper to get values from storage.
   * @param {string|string[]} keys
   * @returns {Promise<object>}
   */
  async _get(keys) {
    return new Promise((resolve, reject) => {
      this._storage.get(keys, (result) => {
        if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve(result);
        }
      });
    });
  }

  /**
   * Internal helper to set values in storage.
   * @param {object} items
   * @returns {Promise<void>}
   */
  async _set(items) {
    return new Promise((resolve, reject) => {
      this._storage.set(items, () => {
        if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve();
        }
      });
    });
  }

  /**
   * Internal helper to remove keys from storage.
   * @param {string|string[]} keys
   * @returns {Promise<void>}
   */
  async _remove(keys) {
    return new Promise((resolve, reject) => {
      this._storage.remove(keys, () => {
        if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve();
        }
      });
    });
  }

  /**
   * Saves a recording session to storage.
   * Stores the full session under `session:{id}` and updates the sessions index.
   * @param {RecordingSession} session
   * @returns {Promise<void>}
   */
  async saveSession(session) {
    const sessionKey = `session:${session.id}`;

    // Build summary for the index
    /** @type {SessionSummary} */
    const summary = {
      id: session.id,
      name: session.name || '',
      startedAt: session.startedAt,
      stoppedAt: session.stoppedAt,
      startingUrl: session.startingUrl,
      actionCount: session.actions ? session.actions.length : 0,
    };

    // Load existing index
    const result = await this._get('sessions');
    const sessions = result.sessions || [];

    // Replace existing entry or append
    const existingIdx = sessions.findIndex(s => s.id === session.id);
    if (existingIdx >= 0) {
      sessions[existingIdx] = summary;
    } else {
      sessions.push(summary);
    }

    // Save both the full session and updated index
    await this._set({
      [sessionKey]: session,
      sessions,
    });
  }

  /**
   * Loads a full recording session from storage by ID.
   * @param {string} sessionId
   * @returns {Promise<RecordingSession|null>}
   */
  async loadSession(sessionId) {
    const sessionKey = `session:${sessionId}`;
    const result = await this._get(sessionKey);
    return result[sessionKey] || null;
  }

  /**
   * Returns an array of SessionSummary objects from the sessions index.
   * @returns {Promise<SessionSummary[]>}
   */
  async listSessions() {
    const result = await this._get('sessions');
    return result.sessions || [];
  }

  /**
   * Deletes a session from storage and removes it from the sessions index.
   * @param {string} sessionId
   * @returns {Promise<void>}
   */
  async deleteSession(sessionId) {
    const sessionKey = `session:${sessionId}`;

    // Update the index
    const result = await this._get('sessions');
    const sessions = (result.sessions || []).filter(s => s.id !== sessionId);

    // Remove the full session data and update the index
    await this._remove(sessionKey);
    await this._set({ sessions });
  }


  /**
   * Checks current storage usage and returns quota information.
   * Shows a warning when usage exceeds 90%.
   * @returns {Promise<StorageQuotaInfo>}
   */
  async checkStorageQuota() {
    const bytesUsed = await new Promise((resolve, reject) => {
      this._storage.getBytesInUse(null, (bytes) => {
        if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve(bytes);
        }
      });
    });

    const bytesTotal = STORAGE_QUOTA_BYTES;
    const percentUsed = (bytesUsed / bytesTotal) * 100;

    return {
      bytesUsed,
      bytesTotal,
      percentUsed,
    };
  }
}
