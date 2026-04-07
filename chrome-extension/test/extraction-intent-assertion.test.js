// Nova Act Recorder - Property Tests for Intent and Assertion features
// Tests for Properties 16, 17, 18

import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import { ActionStore } from '../action-store.js';
import { generateId } from '../session-manager.js';

// ─── Arbitraries ───

const nonEmptyString = fc.string({ minLength: 1, maxLength: 60 })
  .map(s => s.replace(/[\n\r\t]/g, ' ').trim())
  .filter(s => s.length > 0);

const elementDescriptorArb = fc.record({
  text: nonEmptyString,
  tagName: fc.constantFrom('button', 'input', 'a', 'div', 'span', 'textarea'),
  attributes: fc.record({
    id: fc.option(nonEmptyString, { nil: undefined }),
    ariaLabel: fc.option(nonEmptyString, { nil: undefined }),
  }),
});

const urlArb = fc.webUrl();
const scrollDirArb = fc.constantFrom('up', 'down');

/** Builds a RawAction of a given type. */
function makeRawAction(type, element, value, url) {
  return { type, timestamp: Date.now(), url, element, value };
}

/** Arbitrary for a random RawAction. */
const rawActionArb = fc.oneof(
  fc.tuple(elementDescriptorArb, urlArb).map(([el, url]) =>
    makeRawAction('click', el, undefined, url)
  ),
  fc.tuple(elementDescriptorArb, nonEmptyString, urlArb).map(([el, val, url]) =>
    makeRawAction('type', el, val, url)
  ),
  fc.tuple(scrollDirArb, urlArb).map(([dir, url]) =>
    makeRawAction('scroll', undefined, dir, url)
  ),
  urlArb.map(url => makeRawAction('navigation', undefined, url, url))
);

/** Arbitrary for an assertion object. */
const assertionArb = fc.record({
  id: fc.string({ minLength: 5, maxLength: 20 }).filter(s => s.length > 0),
  text: nonEmptyString,
});

// ─── Helpers ───

/**
 * Populates an ActionStore with N random raw actions and returns it.
 */
function buildStore(rawActions) {
  const store = new ActionStore();
  for (const raw of rawActions) {
    store.addAction(raw);
  }
  return store;
}

/**
 * Deep-clones a plain object (for snapshot comparison).
 */
function deepClone(obj) {
  return JSON.parse(JSON.stringify(obj));
}

// ─── Task 8.6.1: Property 16 — Collapse/expand round-trip ───

describe('Property 16: Intent collapse and expand round-trip', () => {
  // Feature: nova-act-recorder, Property 16: Intent collapse and expand round-trip
  // **Validates: Requirements 13.4, 13.7**

  it('collapsing then expanding restores original actions in order', () => {
    fc.assert(
      fc.property(
        fc.array(rawActionArb, { minLength: 2, maxLength: 10 }),
        nonEmptyString,
        (rawActions, intentText) => {
          const store = buildStore(rawActions);
          const originalActions = deepClone(store.getActions());
          const originalLength = originalActions.length;

          // Pick a valid contiguous range
          const startIndex = 0;
          const endIndex = Math.min(originalLength - 1, Math.floor(originalLength / 2));
          const rangeSize = endIndex - startIndex + 1;

          // Collapse
          const collapsed = store.collapseToIntent(startIndex, endIndex, intentText);
          expect(collapsed).not.toBeNull();

          const afterCollapse = store.getActions();
          expect(afterCollapse.length).toBe(originalLength - rangeSize + 1);
          expect(afterCollapse[startIndex].isIntent).toBe(true);
          expect(afterCollapse[startIndex].prompt).toBe(intentText);
          expect(afterCollapse[startIndex].collapsedActions.length).toBe(rangeSize);

          // Expand
          const expanded = store.expandIntent(startIndex);
          expect(expanded).toBe(true);

          const afterExpand = store.getActions();
          expect(afterExpand.length).toBe(originalLength);

          // Verify restored actions match originals
          for (let i = startIndex; i <= endIndex; i++) {
            expect(afterExpand[i].id).toBe(originalActions[i].id);
            expect(afterExpand[i].type).toBe(originalActions[i].type);
            expect(afterExpand[i].prompt).toBe(originalActions[i].prompt);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('collapse with random valid ranges preserves length invariant', () => {
    fc.assert(
      fc.property(
        fc.array(rawActionArb, { minLength: 3, maxLength: 12 }),
        nonEmptyString,
        fc.nat(),
        fc.nat(),
        (rawActions, intentText, rawStart, rawEnd) => {
          const store = buildStore(rawActions);
          const len = store.getActions().length;
          const startIndex = rawStart % len;
          const endIndex = startIndex + (rawEnd % (len - startIndex));
          const clampedEnd = Math.min(endIndex, len - 1);
          const rangeSize = clampedEnd - startIndex + 1;

          store.collapseToIntent(startIndex, clampedEnd, intentText);
          expect(store.getActions().length).toBe(len - rangeSize + 1);

          // Expand back
          store.expandIntent(startIndex);
          expect(store.getActions().length).toBe(len);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('expanding a non-collapsed intent returns false', () => {
    const store = buildStore([makeRawAction('click', { text: 'btn', tagName: 'button', attributes: {} }, undefined, 'https://x.com')]);
    store.addIntentPrompt(0, 'do something');
    const result = store.expandIntent(0);
    expect(result).toBe(false);
  });

  it('invalid indices for collapse return null', () => {
    const store = buildStore([makeRawAction('click', { text: 'btn', tagName: 'button', attributes: {} }, undefined, 'https://x.com')]);
    expect(store.collapseToIntent(-1, 0, 'test')).toBeNull();
    expect(store.collapseToIntent(0, 999, 'test')).toBeNull();
    expect(store.collapseToIntent(1, 0, 'test')).toBeNull();
  });
});

// ─── Task 8.6.2: Property 17 — Intent insertion ───

describe('Property 17: Intent prompt insertion', () => {
  // Feature: nova-act-recorder, Property 17: Intent prompt insertion
  // **Validates: Requirements 13.1**

  it('inserting intent at any valid position increases length by 1 and places intent correctly', () => {
    fc.assert(
      fc.property(
        fc.array(rawActionArb, { minLength: 0, maxLength: 10 }),
        fc.nat({ max: 10 }),
        nonEmptyString,
        (rawActions, rawInsertIndex, intentText) => {
          const store = buildStore(rawActions);
          const originalLength = store.getActions().length;
          const insertIndex = Math.min(rawInsertIndex, originalLength);

          store.addIntentPrompt(insertIndex, intentText);

          const actions = store.getActions();
          expect(actions.length).toBe(originalLength + 1);

          // The entry at insertIndex should be the intent
          const inserted = actions[insertIndex];
          expect(inserted.isIntent).toBe(true);
          expect(inserted.type).toBe('intent');
          expect(inserted.prompt).toBe(intentText);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('inserting intent preserves all existing actions', () => {
    fc.assert(
      fc.property(
        fc.array(rawActionArb, { minLength: 1, maxLength: 8 }),
        fc.nat({ max: 8 }),
        nonEmptyString,
        (rawActions, rawInsertIndex, intentText) => {
          const store = buildStore(rawActions);
          const originalActions = store.getActions().map(a => a.id);
          const insertIndex = Math.min(rawInsertIndex, originalActions.length);

          store.addIntentPrompt(insertIndex, intentText);

          const newActions = store.getActions();
          // All original IDs should still be present
          const newIds = newActions.map(a => a.id);
          for (const id of originalActions) {
            expect(newIds).toContain(id);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('inserting at index 0 places intent at the beginning', () => {
    const store = buildStore([makeRawAction('click', { text: 'btn', tagName: 'button', attributes: {} }, undefined, 'https://x.com')]);
    store.addIntentPrompt(0, 'first intent');
    const actions = store.getActions();
    expect(actions[0].isIntent).toBe(true);
    expect(actions[0].prompt).toBe('first intent');
    expect(actions.length).toBe(2);
  });

  it('inserting beyond length clamps to end', () => {
    const store = buildStore([makeRawAction('click', { text: 'btn', tagName: 'button', attributes: {} }, undefined, 'https://x.com')]);
    store.addIntentPrompt(999, 'end intent');
    const actions = store.getActions();
    expect(actions[actions.length - 1].isIntent).toBe(true);
    expect(actions[actions.length - 1].prompt).toBe('end intent');
  });
});

// ─── Task 9.5.1: Property 18 — Assertion CRUD ───

describe('Property 18: Assertion CRUD on actions', () => {
  // Feature: nova-act-recorder, Property 18: Assertion CRUD on actions
  // **Validates: Requirements 14.4, 14.6, 14.7, 14.8**

  it('adding K assertions results in assertions.length === K', () => {
    fc.assert(
      fc.property(
        fc.array(rawActionArb, { minLength: 1, maxLength: 5 }),
        fc.array(assertionArb, { minLength: 1, maxLength: 5 }),
        (rawActions, assertions) => {
          const store = buildStore(rawActions);
          const actionIndex = 0;

          for (const assertion of assertions) {
            store.addAssertion(actionIndex, assertion);
          }

          const action = store.getActions()[actionIndex];
          expect(action.assertions.length).toBe(assertions.length);

          // Verify each assertion text matches
          for (let i = 0; i < assertions.length; i++) {
            expect(action.assertions[i].text).toBe(assertions[i].text);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('updating assertion at index j changes only that assertion text', () => {
    fc.assert(
      fc.property(
        fc.array(rawActionArb, { minLength: 1, maxLength: 5 }),
        fc.array(assertionArb, { minLength: 2, maxLength: 5 }),
        nonEmptyString,
        fc.nat(),
        (rawActions, assertions, newText, rawIdx) => {
          const store = buildStore(rawActions);
          const actionIndex = 0;

          for (const assertion of assertions) {
            store.addAssertion(actionIndex, assertion);
          }

          const assertionIndex = rawIdx % assertions.length;
          const beforeUpdate = store.getActions()[actionIndex].assertions.map(a => a.text);

          store.updateAssertion(actionIndex, assertionIndex, newText);

          const afterUpdate = store.getActions()[actionIndex].assertions;
          expect(afterUpdate[assertionIndex].text).toBe(newText);

          // All other assertions unchanged
          for (let i = 0; i < afterUpdate.length; i++) {
            if (i !== assertionIndex) {
              expect(afterUpdate[i].text).toBe(beforeUpdate[i]);
            }
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('deleting assertion at index j produces length K-1 without that assertion', () => {
    fc.assert(
      fc.property(
        fc.array(rawActionArb, { minLength: 1, maxLength: 5 }),
        fc.array(assertionArb, { minLength: 1, maxLength: 5 }),
        fc.nat(),
        (rawActions, assertions, rawIdx) => {
          const store = buildStore(rawActions);
          const actionIndex = 0;

          for (const assertion of assertions) {
            store.addAssertion(actionIndex, assertion);
          }

          const K = assertions.length;
          const deleteIdx = rawIdx % K;
          const deletedText = store.getActions()[actionIndex].assertions[deleteIdx].text;

          store.deleteAssertion(actionIndex, deleteIdx);

          const remaining = store.getActions()[actionIndex].assertions;
          expect(remaining.length).toBe(K - 1);

          // The deleted assertion's text should not be at that position
          if (remaining.length > 0 && deleteIdx < remaining.length) {
            // The item that was at deleteIdx+1 should now be at deleteIdx
            expect(remaining[deleteIdx].text).toBe(assertions[deleteIdx + 1].text);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('both positive and negative assertion text are accepted', () => {
    fc.assert(
      fc.property(
        fc.array(rawActionArb, { minLength: 1, maxLength: 3 }),
        nonEmptyString,
        nonEmptyString,
        (rawActions, positiveText, negativeText) => {
          const store = buildStore(rawActions);
          const actionIndex = 0;

          // Positive assertion
          store.addAssertion(actionIndex, { id: 'pos1', text: positiveText, captureScreenshot: false });
          // Negative assertion (with NOT)
          const negText = `${negativeText} should NOT be present`;
          store.addAssertion(actionIndex, { id: 'neg1', text: negText, captureScreenshot: false });

          const action = store.getActions()[actionIndex];
          expect(action.assertions.length).toBe(2);
          expect(action.assertions[0].text).toBe(positiveText);
          expect(action.assertions[1].text).toBe(negText);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('paste action links to last extract_variable variableName', () => {
    const store = new ActionStore();
    const extractRaw = {
      type: 'extract_variable',
      timestamp: Date.now(),
      url: 'https://example.com',
      element: { text: 'price', tagName: 'span', attributes: {} },
      selectedText: '$9.99',
    };
    store.addAction(extractRaw);

    const pasteRaw = {
      type: 'paste',
      timestamp: Date.now(),
      url: 'https://example.com',
      element: { text: 'amount', tagName: 'input', attributes: {} },
      value: '$9.99',
    };
    const pasteEntry = store.addAction(pasteRaw);

    expect(pasteEntry.sourceVariableName).toBe('var_1');
  });

  it('paste with no prior extract_variable has no sourceVariableName', () => {
    const store = new ActionStore();
    const pasteRaw = {
      type: 'paste',
      timestamp: Date.now(),
      url: 'https://example.com',
      element: { text: 'field', tagName: 'input', attributes: {} },
      value: 'hello',
    };
    const pasteEntry = store.addAction(pasteRaw);

    expect(pasteEntry.sourceVariableName).toBeUndefined();
  });

  it('paste links to the most recent extract_variable', () => {
    const store = new ActionStore();
    store.addAction({
      type: 'extract_variable',
      timestamp: Date.now(),
      url: 'https://example.com',
      element: { text: 'first', tagName: 'span', attributes: {} },
      selectedText: 'first',
    });
    store.addAction({
      type: 'extract_variable',
      timestamp: Date.now(),
      url: 'https://example.com',
      element: { text: 'second', tagName: 'span', attributes: {} },
      selectedText: 'second',
    });
    const pasteEntry = store.addAction({
      type: 'paste',
      timestamp: Date.now(),
      url: 'https://example.com',
      element: { text: 'field', tagName: 'input', attributes: {} },
      value: 'second',
    });

    expect(pasteEntry.sourceVariableName).toBe('var_2');
  });

  it('type action after paste on same element is suppressed', () => {
    const store = new ActionStore();
    store.addAction({
      type: 'extract_variable',
      timestamp: Date.now(),
      url: 'https://example.com',
      element: { text: 'Transit Time', tagName: 'span', attributes: {} },
      selectedText: '13.7 yrs / 3 days',
    });
    store.addAction({
      type: 'paste',
      timestamp: Date.now(),
      url: 'https://other.com',
      element: { text: 'Email *', tagName: 'input', attributes: {} },
      value: '13.7 yrs / 3 days',
    });
    // Simulate the race-condition duplicate type from content script blur
    store.addAction({
      type: 'type',
      timestamp: Date.now(),
      url: 'https://other.com',
      element: { text: 'Email *', tagName: 'input', attributes: {} },
      value: '13.7 yrs / 3 days',
    });

    const actions = store.getActions();
    // Should have extract + paste only, no duplicate type
    expect(actions.length).toBe(2);
    expect(actions[0].type).toBe('extract_variable');
    expect(actions[1].type).toBe('paste');
  });

  it('type action after paste on different element is NOT suppressed', () => {
    const store = new ActionStore();
    store.addAction({
      type: 'paste',
      timestamp: Date.now(),
      url: 'https://example.com',
      element: { text: 'Email *', tagName: 'input', attributes: {} },
      value: 'pasted text',
    });
    store.addAction({
      type: 'type',
      timestamp: Date.now(),
      url: 'https://example.com',
      element: { text: 'Name *', tagName: 'input', attributes: {} },
      value: 'typed text',
    });

    const actions = store.getActions();
    expect(actions.length).toBe(2);
    expect(actions[1].type).toBe('type');
  });

  it('out-of-bounds assertion operations are no-ops', () => {
    const store = buildStore([makeRawAction('click', { text: 'btn', tagName: 'button', attributes: {} }, undefined, 'https://x.com')]);
    store.addAssertion(0, { id: 'a1', text: 'test', captureScreenshot: false });

    const before = deepClone(store.getActions());

    // Invalid action index
    store.addAssertion(-1, { id: 'a2', text: 'bad', captureScreenshot: false });
    store.addAssertion(999, { id: 'a3', text: 'bad', captureScreenshot: false });
    store.updateAssertion(-1, 0, 'bad');
    store.updateAssertion(0, 999, 'bad');
    store.deleteAssertion(-1, 0);
    store.deleteAssertion(0, 999);

    // Only the valid assertion should exist
    expect(store.getActions()[0].assertions.length).toBe(1);
    expect(store.getActions()[0].assertions[0].text).toBe('test');
  });
});
