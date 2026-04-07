// Nova Act Recorder - Storage Manager Property Tests
// Tests for session persistence round-trip (Property 11) and session list/delete (Property 12).

import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import { StorageManager } from '../storage-manager.js';

// ─── Mock Chrome Storage Adapter ───

/**
 * In-memory mock of chrome.storage.local for testing.
 * Implements get/set/remove/getBytesInUse with callback-based API.
 */
class MockChromeStorage {
  constructor() {
    /** @type {Map<string, any>} */
    this._store = new Map();
  }

  get(keys, callback) {
    const result = {};
    const keyList = typeof keys === 'string' ? [keys] : (Array.isArray(keys) ? keys : Object.keys(keys || {}));
    for (const key of keyList) {
      if (this._store.has(key)) {
        result[key] = JSON.parse(JSON.stringify(this._store.get(key)));
      }
    }
    callback(result);
  }

  set(items, callback) {
    for (const [key, value] of Object.entries(items)) {
      this._store.set(key, JSON.parse(JSON.stringify(value)));
    }
    if (callback) callback();
  }

  remove(keys, callback) {
    const keyList = typeof keys === 'string' ? [keys] : keys;
    for (const key of keyList) {
      this._store.delete(key);
    }
    if (callback) callback();
  }

  getBytesInUse(keys, callback) {
    let total = 0;
    for (const [, value] of this._store) {
      total += JSON.stringify(value).length;
    }
    callback(total);
  }
}

/** Creates a fresh StorageManager with a clean mock backend. */
function createStorageManager() {
  return new StorageManager(new MockChromeStorage());
}

// ─── Arbitraries ───

const nonEmptyString = fc.string({ minLength: 1, maxLength: 50 })
  .map(s => s.trim())
  .filter(s => s.length > 0);

const urlArb = fc.webUrl();

const assertionArb = fc.record({
  id: fc.uuid(),
  text: nonEmptyString,
});

const actionEntryArb = fc.record({
  id: fc.uuid(),
  type: fc.constantFrom('click', 'type', 'scroll', 'navigation', 'intent'),
  prompt: nonEmptyString,
  promptEdited: fc.boolean(),
  url: urlArb,
  timestamp: fc.integer({ min: 1000000000000, max: 2000000000000 }),
  isIntent: fc.boolean(),
  assertions: fc.array(assertionArb, { minLength: 0, maxLength: 3 }),
});

const recordingSessionArb = fc.record({
  id: fc.uuid(),
  startedAt: fc.integer({ min: 1000000000000, max: 2000000000000 }),
  stoppedAt: fc.option(fc.integer({ min: 1000000000000, max: 2000000000000 }), { nil: undefined }),
  tabId: fc.integer({ min: 1, max: 100000 }),
  startingUrl: urlArb,
  actions: fc.array(actionEntryArb, { minLength: 0, maxLength: 10 }),
});

// ─── Task 10.5.1: Property 11 — Session persistence round-trip ───

describe('Property 11: Session persistence round-trip', () => {
  // Feature: nova-act-recorder, Property 11: Session persistence round-trip
  // **Validates: Requirements 10.1, 10.3**

  it('saving then loading a session should produce identical data', async () => {
    await fc.assert(
      fc.asyncProperty(recordingSessionArb, async (session) => {
        const sm = createStorageManager();

        await sm.saveSession(session);
        const loaded = await sm.loadSession(session.id);

        expect(loaded).not.toBeNull();
        expect(loaded.id).toBe(session.id);
        expect(loaded.startingUrl).toBe(session.startingUrl);
        expect(loaded.startedAt).toBe(session.startedAt);
        expect(loaded.stoppedAt).toBe(session.stoppedAt);
        expect(loaded.tabId).toBe(session.tabId);

        // Verify actions array
        expect(loaded.actions.length).toBe(session.actions.length);
        for (let i = 0; i < session.actions.length; i++) {
          expect(loaded.actions[i].id).toBe(session.actions[i].id);
          expect(loaded.actions[i].type).toBe(session.actions[i].type);
          expect(loaded.actions[i].prompt).toBe(session.actions[i].prompt);
          expect(loaded.actions[i].promptEdited).toBe(session.actions[i].promptEdited);
          expect(loaded.actions[i].url).toBe(session.actions[i].url);
          expect(loaded.actions[i].timestamp).toBe(session.actions[i].timestamp);
          expect(loaded.actions[i].isIntent).toBe(session.actions[i].isIntent);

          // Verify assertions
          expect(loaded.actions[i].assertions.length).toBe(session.actions[i].assertions.length);
          for (let j = 0; j < session.actions[i].assertions.length; j++) {
            expect(loaded.actions[i].assertions[j].id).toBe(session.actions[i].assertions[j].id);
            expect(loaded.actions[i].assertions[j].text).toBe(session.actions[i].assertions[j].text);
            expect(loaded.actions[i].assertions[j].captureScreenshot).toBe(session.actions[i].assertions[j].captureScreenshot);
          }
        }
      }),
      { numRuns: 100 }
    );
  });

  it('saving a session should update the sessions index with correct summary', async () => {
    await fc.assert(
      fc.asyncProperty(recordingSessionArb, async (session) => {
        const sm = createStorageManager();

        await sm.saveSession(session);
        const sessions = await sm.listSessions();

        expect(sessions.length).toBe(1);
        expect(sessions[0].id).toBe(session.id);
        expect(sessions[0].startedAt).toBe(session.startedAt);
        expect(sessions[0].startingUrl).toBe(session.startingUrl);
        expect(sessions[0].actionCount).toBe(session.actions.length);
      }),
      { numRuns: 100 }
    );
  });

  it('loading a non-existent session should return null', async () => {
    await fc.assert(
      fc.asyncProperty(fc.uuid(), async (sessionId) => {
        const sm = createStorageManager();
        const loaded = await sm.loadSession(sessionId);
        expect(loaded).toBeNull();
      }),
      { numRuns: 100 }
    );
  });
});

// ─── Task 10.5.2: Property 12 — Session list and delete ───

describe('Property 12: Session list and delete', () => {
  // Feature: nova-act-recorder, Property 12: Session list and delete
  // **Validates: Requirements 10.2, 10.4**

  it('saving N sessions should produce N summaries with correct data', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.array(recordingSessionArb, { minLength: 1, maxLength: 10 })
          .chain(sessions => {
            // Ensure unique IDs
            const uniqueSessions = [];
            const seen = new Set();
            for (const s of sessions) {
              if (!seen.has(s.id)) {
                seen.add(s.id);
                uniqueSessions.push(s);
              }
            }
            return fc.constant(uniqueSessions.length > 0 ? uniqueSessions : [sessions[0]]);
          }),
        async (sessions) => {
          const sm = createStorageManager();

          for (const session of sessions) {
            await sm.saveSession(session);
          }

          const listed = await sm.listSessions();
          expect(listed.length).toBe(sessions.length);

          for (const session of sessions) {
            const summary = listed.find(s => s.id === session.id);
            expect(summary).toBeDefined();
            expect(summary.startedAt).toBe(session.startedAt);
            expect(summary.actionCount).toBe(session.actions.length);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('deleting a subset of sessions should leave the correct count and loadSession should return null for deleted', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.array(recordingSessionArb, { minLength: 2, maxLength: 8 })
          .chain(sessions => {
            const uniqueSessions = [];
            const seen = new Set();
            for (const s of sessions) {
              if (!seen.has(s.id)) {
                seen.add(s.id);
                uniqueSessions.push(s);
              }
            }
            return fc.constant(uniqueSessions.length >= 2 ? uniqueSessions : null);
          })
          .filter(s => s !== null),
        fc.integer({ min: 1, max: 100 }),
        async (sessions, deleteRaw) => {
          const sm = createStorageManager();

          // Save all sessions
          for (const session of sessions) {
            await sm.saveSession(session);
          }

          // Determine how many to delete (at least 1, at most sessions.length - 1)
          const deleteCount = (deleteRaw % (sessions.length - 1)) + 1;
          const toDelete = sessions.slice(0, deleteCount);
          const toKeep = sessions.slice(deleteCount);

          // Delete the subset
          for (const session of toDelete) {
            await sm.deleteSession(session.id);
          }

          // Verify list count
          const listed = await sm.listSessions();
          expect(listed.length).toBe(toKeep.length);

          // Verify deleted sessions return null on load
          for (const session of toDelete) {
            const loaded = await sm.loadSession(session.id);
            expect(loaded).toBeNull();
          }

          // Verify kept sessions are still loadable
          for (const session of toKeep) {
            const loaded = await sm.loadSession(session.id);
            expect(loaded).not.toBeNull();
            expect(loaded.id).toBe(session.id);
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});
