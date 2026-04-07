// Nova Act Recorder - Background Service Worker Property Tests
// Tests for SessionManager, ActionStore, tab-scoping, and state recovery.

import { describe, it, expect, beforeEach } from 'vitest';
import fc from 'fast-check';
import { SessionManager, generateId } from '../session-manager.js';
import { ActionStore, generatePlaceholderPrompt, shouldConsolidateScroll } from '../action-store.js';

// ─── Arbitraries ───

/** Generates a valid URL string. */
const urlArb = fc.webUrl();

/** Generates a positive tab ID. */
const tabIdArb = fc.integer({ min: 1, max: 100000 });

/** Generates a non-empty trimmed string. */
const nonEmptyString = fc.string({ minLength: 1, maxLength: 60 })
  .map(s => s.trim())
  .filter(s => s.length > 0);

/** Generates a mock ElementDescriptor. */
const elementDescriptorArb = fc.record({
  text: nonEmptyString,
  tagName: fc.constantFrom('button', 'input', 'a', 'div', 'span', 'textarea', 'select', 'p'),
  attributes: fc.record({
    id: fc.option(nonEmptyString, { nil: undefined }),
    ariaLabel: fc.option(nonEmptyString, { nil: undefined }),
    role: fc.option(nonEmptyString, { nil: undefined }),
    placeholder: fc.option(nonEmptyString, { nil: undefined }),
    name: fc.option(nonEmptyString, { nil: undefined }),
    type: fc.option(fc.constantFrom('text', 'password', 'submit', 'button', 'checkbox'), { nil: undefined }),
  }),
});

/** Generates a scroll direction. */
const scrollDirArb = fc.constantFrom('up', 'down');

/** Generates a RawAction of a specific type. */
const clickActionArb = fc.record({
  type: fc.constant('click'),
  timestamp: fc.integer({ min: 1000000000000, max: 2000000000000 }),
  url: urlArb,
  element: elementDescriptorArb,
});

const typeActionArb = fc.record({
  type: fc.constant('type'),
  timestamp: fc.integer({ min: 1000000000000, max: 2000000000000 }),
  url: urlArb,
  element: elementDescriptorArb,
  value: nonEmptyString,
});

const scrollActionArb = fc.record({
  type: fc.constant('scroll'),
  timestamp: fc.integer({ min: 1000000000000, max: 2000000000000 }),
  url: urlArb,
  value: scrollDirArb,
});

const navigationActionArb = fc.record({
  type: fc.constant('navigation'),
  timestamp: fc.integer({ min: 1000000000000, max: 2000000000000 }),
  url: urlArb,
  value: urlArb,
});

const tabSwitchActionArb = fc.record({
  type: fc.constant('tab_switch'),
  timestamp: fc.integer({ min: 1000000000000, max: 2000000000000 }),
  url: urlArb,
  value: urlArb,
  tabTitle: nonEmptyString,
});

/** Generates a RawAction of any type. */
const rawActionArb = fc.oneof(clickActionArb, typeActionArb, scrollActionArb, navigationActionArb, tabSwitchActionArb);

/** Generates a non-scroll RawAction (for sequences where we don't want consolidation). */
const nonScrollActionArb = fc.oneof(clickActionArb, typeActionArb, navigationActionArb, tabSwitchActionArb);

// ─── Task 3.6.1: Property 1 — Recording session lifecycle preserves actions ───

describe('Property 1: Recording session lifecycle preserves actions', () => {
  // Feature: nova-act-recorder, Property 1: Recording session lifecycle preserves actions
  // **Validates: Requirements 1.1, 1.3, 1.4**

  it('should preserve all added actions after start/stop and isRecording should be false after stop', () => {
    fc.assert(
      fc.property(
        tabIdArb,
        urlArb,
        fc.array(nonScrollActionArb, { minLength: 0, maxLength: 20 }),
        (tabId, startUrl, actions) => {
          const sm = new SessionManager();
          const store = new ActionStore();

          // Start recording
          sm.startRecording(tabId, startUrl);
          expect(sm.isRecording()).toBe(true);

          // The initial navigation action is added by startRecording
          store.setActions(sm.getActions());

          // Add all actions
          for (const action of actions) {
            const entry = store.addAction(action);
            sm.setActions(store.getActionsRef());
          }

          // Stop recording
          const session = sm.stopRecording();

          // isRecording should be false
          expect(sm.isRecording()).toBe(false);

          // Session should exist
          expect(session).not.toBeNull();

          // All actions should be preserved (initial nav + added actions)
          const resultActions = store.getActions();
          // First action should be navigation
          expect(resultActions[0].type).toBe('navigation');
          // Total count: 1 initial nav + number of added actions
          expect(resultActions.length).toBe(1 + actions.length);

          // Each added action should be present in order
          for (let i = 0; i < actions.length; i++) {
            expect(resultActions[i + 1].type).toBe(actions[i].type);
            expect(resultActions[i + 1].url).toBe(actions[i].url);
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});


// ─── Task 3.6.2: Property 3 — Captured actions contain required fields ───

describe('Property 3: Captured actions contain required fields', () => {
  // Feature: nova-act-recorder, Property 3: Captured actions contain required fields
  // **Validates: Requirements 2.1, 2.4, 3.2, 3.3, 4.1, 5.1**

  it('click actions should include non-empty url and element descriptor', () => {
    fc.assert(
      fc.property(clickActionArb, (rawAction) => {
        const store = new ActionStore();
        const entry = store.addAction(rawAction);

        expect(entry.url).toBeTruthy();
        expect(entry.url.length).toBeGreaterThan(0);
        expect(entry.type).toBe('click');
        expect(rawAction.element).toBeDefined();
        expect(rawAction.element.text).toBeTruthy();
        expect(entry.id).toBeTruthy();
        expect(entry.prompt).toBeTruthy();
      }),
      { numRuns: 100 }
    );
  });

  it('typing actions should include non-empty element descriptor and value', () => {
    fc.assert(
      fc.property(typeActionArb, (rawAction) => {
        const store = new ActionStore();
        const entry = store.addAction(rawAction);

        expect(entry.url).toBeTruthy();
        expect(entry.type).toBe('type');
        expect(rawAction.element).toBeDefined();
        expect(rawAction.element.text).toBeTruthy();
        expect(rawAction.value).toBeTruthy();
        expect(rawAction.value.length).toBeGreaterThan(0);
        expect(entry.id).toBeTruthy();
      }),
      { numRuns: 100 }
    );
  });

  it('scroll actions should include value of "up" or "down"', () => {
    fc.assert(
      fc.property(scrollActionArb, (rawAction) => {
        const store = new ActionStore();
        const entry = store.addAction(rawAction);

        expect(entry.url).toBeTruthy();
        expect(entry.type).toBe('scroll');
        expect(['up', 'down']).toContain(rawAction.value);
        expect(entry.id).toBeTruthy();
      }),
      { numRuns: 100 }
    );
  });

  it('navigation actions should include non-empty url in value field', () => {
    fc.assert(
      fc.property(navigationActionArb, (rawAction) => {
        const store = new ActionStore();
        const entry = store.addAction(rawAction);

        expect(entry.url).toBeTruthy();
        expect(entry.type).toBe('navigation');
        expect(rawAction.value).toBeTruthy();
        expect(rawAction.value.length).toBeGreaterThan(0);
        expect(entry.id).toBeTruthy();
      }),
      { numRuns: 100 }
    );
  });

  it('tab_switch actions should include non-empty url and tabTitle', () => {
    fc.assert(
      fc.property(tabSwitchActionArb, (rawAction) => {
        const store = new ActionStore();
        const entry = store.addAction(rawAction);

        expect(entry.url).toBeTruthy();
        expect(entry.type).toBe('tab_switch');
        expect(rawAction.tabTitle).toBeTruthy();
        expect(rawAction.value).toBeTruthy();
        expect(entry.id).toBeTruthy();
        expect(entry.prompt).toBeTruthy();
        expect(entry.prompt).toContain('switch to tab');
      }),
      { numRuns: 100 }
    );
  });

  it('all action types should have required base fields', () => {
    fc.assert(
      fc.property(rawActionArb, (rawAction) => {
        const store = new ActionStore();
        const entry = store.addAction(rawAction);

        // Every entry must have these fields
        expect(entry.id).toBeTruthy();
        expect(typeof entry.id).toBe('string');
        expect(entry.type).toBeTruthy();
        expect(entry.url).toBeTruthy();
        expect(typeof entry.timestamp).toBe('number');
        expect(entry.prompt).toBeTruthy();
        expect(typeof entry.promptEdited).toBe('boolean');
        expect(entry.promptEdited).toBe(false);
        expect(entry.isIntent).toBe(false);
        expect(Array.isArray(entry.assertions)).toBe(true);
      }),
      { numRuns: 100 }
    );
  });
});


// ─── Task 3.6.3: Property 5 — Scroll consolidation ───

describe('Property 5: Scroll consolidation', () => {
  // Feature: nova-act-recorder, Property 5: Scroll consolidation
  // **Validates: Requirements 4.2, 4.3**

  it('consecutive same-direction scrolls should produce exactly one scroll action', () => {
    fc.assert(
      fc.property(
        scrollDirArb,
        fc.integer({ min: 2, max: 20 }),
        urlArb,
        (direction, count, url) => {
          const store = new ActionStore();

          // Add multiple consecutive same-direction scrolls
          for (let i = 0; i < count; i++) {
            store.addAction({
              type: 'scroll',
              timestamp: Date.now() + i,
              url,
              value: direction,
            });
          }

          const actions = store.getActions();
          // Should be consolidated into exactly one scroll action
          expect(actions.length).toBe(1);
          expect(actions[0].type).toBe('scroll');
          expect(actions[0].rawAction.value).toBe(direction);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('a direction change should start a new scroll action', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 5 }),
        fc.integer({ min: 1, max: 5 }),
        urlArb,
        (countDown, countUp, url) => {
          const store = new ActionStore();

          // Add scrolls down
          for (let i = 0; i < countDown; i++) {
            store.addAction({
              type: 'scroll',
              timestamp: Date.now() + i,
              url,
              value: 'down',
            });
          }

          // Add scrolls up
          for (let i = 0; i < countUp; i++) {
            store.addAction({
              type: 'scroll',
              timestamp: Date.now() + countDown + i,
              url,
              value: 'up',
            });
          }

          const actions = store.getActions();
          // Should have exactly 2 scroll actions (one down, one up)
          expect(actions.length).toBe(2);
          expect(actions[0].rawAction.value).toBe('down');
          expect(actions[1].rawAction.value).toBe('up');
        }
      ),
      { numRuns: 100 }
    );
  });

  it('a non-scroll action between scrolls should break consolidation', () => {
    fc.assert(
      fc.property(
        scrollDirArb,
        nonScrollActionArb,
        urlArb,
        (direction, interruptAction, url) => {
          const store = new ActionStore();

          // First scroll
          store.addAction({
            type: 'scroll',
            timestamp: Date.now(),
            url,
            value: direction,
          });

          // Non-scroll action in between
          store.addAction(interruptAction);

          // Second scroll (same direction)
          store.addAction({
            type: 'scroll',
            timestamp: Date.now() + 2,
            url,
            value: direction,
          });

          const actions = store.getActions();
          // Should have 3 actions: scroll, non-scroll, scroll
          expect(actions.length).toBe(3);
          expect(actions[0].type).toBe('scroll');
          expect(actions[1].type).toBe(interruptAction.type);
          expect(actions[2].type).toBe('scroll');
        }
      ),
      { numRuns: 100 }
    );
  });

  it('alternating scroll directions should produce one action per direction change', () => {
    fc.assert(
      fc.property(
        fc.array(scrollDirArb, { minLength: 1, maxLength: 30 }),
        urlArb,
        (directions, url) => {
          const store = new ActionStore();

          for (let i = 0; i < directions.length; i++) {
            store.addAction({
              type: 'scroll',
              timestamp: Date.now() + i,
              url,
              value: directions[i],
            });
          }

          const actions = store.getActions();

          // Count expected actions: one per run of same direction
          let expectedCount = 1;
          for (let i = 1; i < directions.length; i++) {
            if (directions[i] !== directions[i - 1]) {
              expectedCount++;
            }
          }

          expect(actions.length).toBe(expectedCount);
          // All should be scroll actions
          for (const a of actions) {
            expect(a.type).toBe('scroll');
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});


// ─── Task 3.6.4: Property 6 — Initial navigation recorded ───

describe('Property 6: Initial navigation recorded', () => {
  // Feature: nova-act-recorder, Property 6: Initial navigation recorded
  // **Validates: Requirements 5.2**

  it('first action in any session should be a navigation action matching the starting URL', () => {
    fc.assert(
      fc.property(
        tabIdArb,
        urlArb,
        fc.array(nonScrollActionArb, { minLength: 0, maxLength: 10 }),
        (tabId, startUrl, additionalActions) => {
          const sm = new SessionManager();
          const store = new ActionStore();

          sm.startRecording(tabId, startUrl);
          store.setActions(sm.getActions());

          // Add additional actions
          for (const action of additionalActions) {
            store.addAction(action);
          }

          const actions = store.getActions();

          // First action must be navigation
          expect(actions.length).toBeGreaterThanOrEqual(1);
          expect(actions[0].type).toBe('navigation');
          expect(actions[0].url).toBe(startUrl);
          expect(actions[0].rawAction.value).toBe(startUrl);
          expect(actions[0].prompt).toContain(startUrl);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('session startingUrl should match the first navigation action URL', () => {
    fc.assert(
      fc.property(tabIdArb, urlArb, (tabId, startUrl) => {
        const sm = new SessionManager();
        const session = sm.startRecording(tabId, startUrl);

        expect(session.startingUrl).toBe(startUrl);
        expect(session.actions[0].type).toBe('navigation');
        expect(session.actions[0].url).toBe(startUrl);
      }),
      { numRuns: 100 }
    );
  });
});


// ─── Task 3.6.5: Property 8 — Action log edit operations ───

describe('Property 8: Action log edit operations', () => {
  // Feature: nova-act-recorder, Property 8: Action log edit operations
  // **Validates: Requirements 7.2, 7.3, 7.4, 7.5, 13.8**

  /**
   * Helper: creates an ActionStore pre-populated with N non-scroll actions.
   */
  function createPopulatedStore(actions) {
    const store = new ActionStore();
    for (const a of actions) {
      store.addAction(a);
    }
    return store;
  }

  it('updatePrompt should set prompt text and promptEdited=true', () => {
    fc.assert(
      fc.property(
        fc.array(nonScrollActionArb, { minLength: 1, maxLength: 15 }),
        nonEmptyString,
        (actions, newPrompt) => {
          const store = createPopulatedStore(actions);
          const idx = 0;
          const originalId = store.getActions()[idx].id;

          store.updatePrompt(idx, newPrompt);

          const updated = store.getActions()[idx];
          expect(updated.prompt).toBe(newPrompt);
          expect(updated.promptEdited).toBe(true);
          expect(updated.id).toBe(originalId);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('reorderAction should move action and preserve all others', () => {
    fc.assert(
      fc.property(
        fc.array(nonScrollActionArb, { minLength: 2, maxLength: 15 }),
        (actions) => {
          const store = createPopulatedStore(actions);
          const n = store.length;
          const fromIndex = 0;
          const toIndex = n - 1;

          const idsBefore = store.getActions().map(a => a.id);
          const movedId = idsBefore[fromIndex];

          store.reorderAction(fromIndex, toIndex);

          const idsAfter = store.getActions().map(a => a.id);

          // Same length
          expect(idsAfter.length).toBe(n);
          // The moved item should be at toIndex
          expect(idsAfter[toIndex]).toBe(movedId);
          // All original IDs should still be present
          expect(new Set(idsAfter)).toEqual(new Set(idsBefore));
        }
      ),
      { numRuns: 100 }
    );
  });

  it('deleteAction should produce log of length N-1 without the deleted action', () => {
    fc.assert(
      fc.property(
        fc.array(nonScrollActionArb, { minLength: 1, maxLength: 15 }),
        (actions) => {
          const store = createPopulatedStore(actions);
          const n = store.length;
          const idx = 0;
          const deletedId = store.getActions()[idx].id;

          store.deleteAction(idx);

          const remaining = store.getActions();
          expect(remaining.length).toBe(n - 1);
          // Deleted action should not be present
          expect(remaining.find(a => a.id === deletedId)).toBeUndefined();
        }
      ),
      { numRuns: 100 }
    );
  });

  it('clearAll should produce an empty log', () => {
    fc.assert(
      fc.property(
        fc.array(nonScrollActionArb, { minLength: 0, maxLength: 15 }),
        (actions) => {
          const store = createPopulatedStore(actions);
          store.clearAll();
          expect(store.getActions().length).toBe(0);
          expect(store.length).toBe(0);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('random sequence of edit operations should maintain valid state', () => {
    // Operation types: updatePrompt, reorderAction, deleteAction
    const operationArb = fc.oneof(
      fc.record({ op: fc.constant('update'), prompt: nonEmptyString }),
      fc.constant({ op: 'reorder' }),
      fc.constant({ op: 'delete' }),
    );

    fc.assert(
      fc.property(
        fc.array(nonScrollActionArb, { minLength: 3, maxLength: 10 }),
        fc.array(operationArb, { minLength: 1, maxLength: 10 }),
        (actions, operations) => {
          const store = createPopulatedStore(actions);

          for (const operation of operations) {
            const n = store.length;
            if (n === 0) break;

            switch (operation.op) {
              case 'update': {
                const idx = Math.floor(Math.random() * n);
                store.updatePrompt(idx, operation.prompt);
                expect(store.getActions()[idx].prompt).toBe(operation.prompt);
                expect(store.getActions()[idx].promptEdited).toBe(true);
                break;
              }
              case 'reorder': {
                if (n < 2) break;
                const from = 0;
                const to = n - 1;
                const idsBefore = store.getActions().map(a => a.id);
                store.reorderAction(from, to);
                const idsAfter = store.getActions().map(a => a.id);
                expect(idsAfter.length).toBe(idsBefore.length);
                expect(new Set(idsAfter)).toEqual(new Set(idsBefore));
                break;
              }
              case 'delete': {
                const idx = 0;
                const prevLen = store.length;
                store.deleteAction(idx);
                expect(store.length).toBe(prevLen - 1);
                break;
              }
            }
          }

          // After all operations, all remaining actions should have valid fields
          for (const action of store.getActions()) {
            expect(action.id).toBeTruthy();
            expect(action.type).toBeTruthy();
            expect(action.prompt).toBeTruthy();
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});


// ─── Task 3.6.6: Property 10 — Tab-scoped recording ───

describe('Property 10: Tab-scoped recording', () => {
  // Feature: nova-act-recorder, Property 10: Tab-scoped recording
  // **Validates: Requirements 9.1, 9.2, 9.3**

  it('should only capture actions from the recording tab', () => {
    fc.assert(
      fc.property(
        tabIdArb,
        urlArb,
        fc.array(
          fc.record({
            action: nonScrollActionArb,
            tabId: tabIdArb,
          }),
          { minLength: 1, maxLength: 20 }
        ),
        (recordingTabId, startUrl, actionWithTabs) => {
          const sm = new SessionManager();
          const store = new ActionStore();

          sm.startRecording(recordingTabId, startUrl);
          store.setActions(sm.getActions());

          let expectedCount = 1; // initial navigation

          for (const { action, tabId } of actionWithTabs) {
            if (sm.shouldCaptureAction(tabId)) {
              store.addAction(action);
              expectedCount++;
            }
          }

          const actions = store.getActions();
          expect(actions.length).toBe(expectedCount);

          // All captured actions should be from the recording tab context
          // (they were only added if shouldCaptureAction returned true)
        }
      ),
      { numRuns: 100 }
    );
  });

  it('should reject actions from non-recording tabs', () => {
    fc.assert(
      fc.property(
        tabIdArb,
        urlArb,
        nonScrollActionArb,
        (recordingTabId, startUrl, action) => {
          const sm = new SessionManager();

          sm.startRecording(recordingTabId, startUrl);

          // Use a different tab ID
          const otherTabId = recordingTabId + 1;
          expect(sm.shouldCaptureAction(otherTabId)).toBe(false);
          expect(sm.shouldCaptureAction(recordingTabId)).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('should move recording to the new tab on tab switch', () => {
    fc.assert(
      fc.property(
        tabIdArb,
        urlArb,
        tabIdArb.filter(id => id > 1), // ensure we can get a different tab
        (recordingTabId, startUrl, otherTabBase) => {
          const otherTabId = recordingTabId === otherTabBase ? otherTabBase + 1 : otherTabBase;
          const sm = new SessionManager();

          sm.startRecording(recordingTabId, startUrl);

          // Initially should capture from recording tab
          expect(sm.shouldCaptureAction(recordingTabId)).toBe(true);
          expect(sm.isPaused()).toBe(false);

          // Switch to another tab — recording follows
          sm.handleTabActivated(otherTabId);
          expect(sm.isPaused()).toBe(false);
          expect(sm.getActiveTabId()).toBe(otherTabId);
          expect(sm.shouldCaptureAction(otherTabId)).toBe(true);
          expect(sm.shouldCaptureAction(recordingTabId)).toBe(false);

          // Switch back — recording follows again
          sm.handleTabActivated(recordingTabId);
          expect(sm.isPaused()).toBe(false);
          expect(sm.getActiveTabId()).toBe(recordingTabId);
          expect(sm.shouldCaptureAction(recordingTabId)).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('should capture actions on the new tab after switching', () => {
    fc.assert(
      fc.property(
        tabIdArb,
        urlArb,
        fc.array(nonScrollActionArb, { minLength: 1, maxLength: 10 }),
        (recordingTabId, startUrl, actions) => {
          const sm = new SessionManager();
          const store = new ActionStore();
          const otherTabId = recordingTabId + 1;

          sm.startRecording(recordingTabId, startUrl);
          store.setActions(sm.getActions());

          // Switch to another tab
          sm.handleTabActivated(otherTabId);

          // Actions from the new tab should be captured
          for (const action of actions) {
            if (sm.shouldCaptureAction(otherTabId)) {
              store.addAction(action);
            }
          }

          expect(store.getActions().length).toBe(1 + actions.length);
        }
      ),
      { numRuns: 100 }
    );
  });
});


// ─── CDP Bridge: START_RECORDING_FROM_CDP contract ───

describe('CDP Bridge: START_RECORDING_FROM_CDP contract', () => {
  // Tests the SessionManager behavior that backs the START_RECORDING_FROM_CDP
  // message handler used by the content script's window.__novaRecorderStartRecording()

  it('should start recording using sender tab ID and URL (simulating CDP bridge)', () => {
    fc.assert(
      fc.property(tabIdArb, urlArb, (senderTabId, pageUrl) => {
        const sm = new SessionManager();
        const store = new ActionStore();

        // Simulate what START_RECORDING_FROM_CDP does:
        // uses sender.tab.id (senderTabId) and message.url (pageUrl)
        store.clearAll();
        const session = sm.startRecording(senderTabId, pageUrl);
        store.setActions(sm.getActions());

        // Session should be created with the sender's tab ID
        expect(session).not.toBeNull();
        expect(session.tabId).toBe(senderTabId);
        expect(session.startingUrl).toBe(pageUrl);
        expect(sm.isRecording()).toBe(true);

        // Should have initial navigation action
        expect(session.actions.length).toBe(1);
        expect(session.actions[0].type).toBe('navigation');
        expect(session.actions[0].url).toBe(pageUrl);
      }),
      { numRuns: 100 }
    );
  });

  it('should produce a serialized session with tabId on stop (CDP stopRecording contract)', () => {
    fc.assert(
      fc.property(
        tabIdArb,
        urlArb,
        fc.array(nonScrollActionArb, { minLength: 0, maxLength: 10 }),
        (tabId, startUrl, actions) => {
          const sm = new SessionManager();
          const store = new ActionStore();

          sm.startRecording(tabId, startUrl);
          store.setActions(sm.getActions());

          for (const action of actions) {
            store.addAction(action);
            sm.setActions(store.getActionsRef());
          }

          const session = sm.stopRecording();

          // The session returned by stopRecording must include tabId
          // (this is what serializeRecording receives and must pass through)
          expect(session).not.toBeNull();
          expect(session.tabId).toBe(tabId);
          expect(session.id).toBeTruthy();
          expect(session.startedAt).toBeGreaterThan(0);
          expect(session.stoppedAt).toBeGreaterThan(0);
          expect(session.startingUrl).toBe(startUrl);
          expect(session.actions.length).toBe(1 + actions.length);
        }
      ),
      { numRuns: 100 }
    );
  });
});
