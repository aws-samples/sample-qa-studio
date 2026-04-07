import { describe, it, expect } from 'vitest';
import fc from 'fast-check';

describe('Project setup verification', () => {
  it('vitest runs correctly', () => {
    expect(1 + 1).toBe(2);
  });

  it('fast-check is available and runs property tests', () => {
    fc.assert(
      fc.property(fc.integer(), fc.integer(), (a, b) => {
        return a + b === b + a;
      }),
      { numRuns: 100 }
    );
  });
});

describe('Type definitions smoke test', () => {
  it('can create an ElementDescriptor-shaped object', () => {
    /** @type {import("../types.js").ElementDescriptor} */
    const descriptor = {
      text: 'Submit',
      tagName: 'button',
      attributes: {
        id: 'submit-btn',
        ariaLabel: 'Submit form',
        role: 'button'
      }
    };
    expect(descriptor.text).toBe('Submit');
    expect(descriptor.tagName).toBe('button');
    expect(descriptor.attributes.id).toBe('submit-btn');
  });

  it('can create an ActionEntry-shaped object', () => {
    /** @type {import("../types.js").ActionEntry} */
    const entry = {
      id: 'test-uuid',
      type: 'click',
      prompt: "click on 'Submit' button",
      promptEdited: false,
      url: 'https://example.com',
      timestamp: Date.now(),
      isIntent: false,
      assertions: []
    };
    expect(entry.type).toBe('click');
    expect(entry.assertions).toEqual([]);
  });

  it('can create a RecordingSession-shaped object', () => {
    /** @type {import("../types.js").RecordingSession} */
    const session = {
      id: 'session-uuid',
      startedAt: Date.now(),
      tabId: 1,
      startingUrl: 'https://example.com',
      actions: []
    };
    expect(session.id).toBe('session-uuid');
    expect(session.actions).toEqual([]);
  });

  it('can create an Assertion-shaped object', () => {
    /** @type {import("../types.js").Assertion} */
    const assertion = {
      id: 'assertion-uuid',
      text: 'the cart should show 1 item',
    };
    expect(assertion.text).toBe('the cart should show 1 item');
  });

});
