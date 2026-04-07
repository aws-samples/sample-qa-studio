// Nova Act Recorder - Recording Serializer Tests
// Tests for serializeRecording() and serializeActions()

'use strict';

import { describe, it, expect } from 'vitest';
import { serializeRecording, serializeActions } from '../recording-serializer.js';

describe('serializeRecording', () => {
  it('should remove rawAction, collapsedActions, and promptEdited from ActionEntry', () => {
    /** @type {import('../types.js').RecordingSession} */
    const session = {
      id: 'session-1',
      startedAt: 1000,
      stoppedAt: 2000,
      tabId: 123,
      startingUrl: 'https://example.com',
      actions: [
        {
          id: 'action-1',
          type: 'click',
          rawAction: { type: 'click', timestamp: 1000, url: 'https://example.com' },
          prompt: 'click on button',
          promptEdited: false,
          url: 'https://example.com',
          timestamp: 1000,
          isIntent: false,
          assertions: [],
        },
      ],
    };

    const serialized = serializeRecording(session);

    expect(serialized.actions[0]).not.toHaveProperty('rawAction');
    expect(serialized.actions[0]).not.toHaveProperty('promptEdited');
    expect(serialized.actions[0]).toHaveProperty('prompt');
    expect(serialized.actions[0]).toHaveProperty('type');
    expect(serialized.actions[0]).toHaveProperty('id');
  });

  it('should remove outerHTML, cssClasses, and dataAttributes from ElementDescriptor', () => {
    /** @type {import('../types.js').RecordingSession} */
    const session = {
      id: 'session-1',
      startedAt: 1000,
      stoppedAt: 2000,
      tabId: 123,
      startingUrl: 'https://example.com',
      actions: [
        {
          id: 'action-1',
          type: 'click',
          rawAction: {
            type: 'click',
            timestamp: 1000,
            url: 'https://example.com',
            element: {
              text: 'Submit',
              tagName: 'button',
              attributes: { id: 'submit-btn' },
              cssClasses: ['btn', 'btn-primary'],
              dataAttributes: { testid: 'submit' },
              outerHTML: '<button id="submit-btn" class="btn btn-primary" data-testid="submit">Submit</button>',
              ancestorPath: 'form > div > button',
            },
          },
          prompt: 'click on Submit button',
          promptEdited: false,
          url: 'https://example.com',
          timestamp: 1000,
          isIntent: false,
          assertions: [],
        },
      ],
    };

    const serialized = serializeRecording(session);
    const action = serialized.actions[0];

    // rawAction itself should be removed, so element won't exist in serialized form
    expect(action).not.toHaveProperty('rawAction');
  });

  it('should preserve assertions on serialized actions', () => {
    /** @type {import('../types.js').RecordingSession} */
    const session = {
      id: 'session-1',
      startedAt: 1000,
      stoppedAt: 2000,
      tabId: 123,
      startingUrl: 'https://example.com',
      actions: [
        {
          id: 'action-1',
          type: 'click',
          rawAction: { type: 'click', timestamp: 1000, url: 'https://example.com' },
          prompt: 'click on button',
          promptEdited: false,
          url: 'https://example.com',
          timestamp: 1000,
          isIntent: false,
          assertions: [
            { id: 'assertion-1', text: 'button should be visible' },
          ],
        },
      ],
    };

    const serialized = serializeRecording(session);
    const assertion = serialized.actions[0].assertions[0];

    expect(assertion).toHaveProperty('id', 'assertion-1');
    expect(assertion).toHaveProperty('text', 'button should be visible');
  });

  it('should remove collapsedActions from intent actions', () => {
    /** @type {import('../types.js').RecordingSession} */
    const session = {
      id: 'session-1',
      startedAt: 1000,
      stoppedAt: 2000,
      tabId: 123,
      startingUrl: 'https://example.com',
      actions: [
        {
          id: 'action-1',
          type: 'intent',
          prompt: 'log in with credentials',
          promptEdited: false,
          url: 'https://example.com',
          timestamp: 1000,
          isIntent: true,
          assertions: [],
          collapsedActions: [
            {
              id: 'action-2',
              type: 'type',
              rawAction: { type: 'type', timestamp: 1000, url: 'https://example.com', value: 'user@example.com' },
              prompt: 'type user@example.com',
              promptEdited: false,
              url: 'https://example.com',
              timestamp: 1000,
              isIntent: false,
              assertions: [],
            },
            {
              id: 'action-3',
              type: 'click',
              rawAction: { type: 'click', timestamp: 1001, url: 'https://example.com' },
              prompt: 'click on Login button',
              promptEdited: false,
              url: 'https://example.com',
              timestamp: 1001,
              isIntent: false,
              assertions: [],
            },
          ],
        },
      ],
    };

    const serialized = serializeRecording(session);

    expect(serialized.actions[0]).not.toHaveProperty('collapsedActions');
    expect(serialized.actions[0]).toHaveProperty('isIntent');
    expect(serialized.actions[0].isIntent).toBe(true);
  });

  it('should handle null session', () => {
    const serialized = serializeRecording(null);
    expect(serialized).toBe(null);
  });

  it('should preserve essential fields', () => {
    /** @type {import('../types.js').RecordingSession} */
    const session = {
      id: 'session-1',
      startedAt: 1000,
      stoppedAt: 2000,
      tabId: 123,
      startingUrl: 'https://example.com',
      name: 'Test Session',
      actions: [
        {
          id: 'action-1',
          type: 'navigation',
          rawAction: { type: 'navigation', timestamp: 1000, url: 'https://example.com', value: 'https://example.com' },
          prompt: 'navigate to https://example.com',
          promptEdited: false,
          url: 'https://example.com',
          timestamp: 1000,
          isIntent: false,
          assertions: [],
        },
      ],
    };

    const serialized = serializeRecording(session);

    expect(serialized.id).toBe('session-1');
    expect(serialized.startedAt).toBe(1000);
    expect(serialized.stoppedAt).toBe(2000);
    expect(serialized.tabId).toBe(123);
    expect(serialized.startingUrl).toBe('https://example.com');
    expect(serialized.name).toBe('Test Session');
    expect(serialized.actions).toHaveLength(1);
    expect(serialized.actions[0].id).toBe('action-1');
    expect(serialized.actions[0].type).toBe('navigation');
    expect(serialized.actions[0].prompt).toBe('navigate to https://example.com');
    expect(serialized.actions[0].url).toBe('https://example.com');
    expect(serialized.actions[0].timestamp).toBe(1000);
  });

  it('should handle actions with element descriptors', () => {
    /** @type {import('../types.js').RecordingSession} */
    const session = {
      id: 'session-1',
      startedAt: 1000,
      stoppedAt: 2000,
      tabId: 123,
      startingUrl: 'https://example.com',
      actions: [
        {
          id: 'action-1',
          type: 'click',
          rawAction: {
            type: 'click',
            timestamp: 1000,
            url: 'https://example.com',
            element: {
              text: 'Submit',
              tagName: 'button',
              attributes: { id: 'submit-btn', role: 'button' },
              cssClasses: ['btn'],
              dataAttributes: { testid: 'submit' },
              outerHTML: '<button>Submit</button>',
              ancestorPath: 'form > div',
            },
          },
          prompt: 'click on Submit button',
          promptEdited: false,
          url: 'https://example.com',
          timestamp: 1000,
          isIntent: false,
          assertions: [],
          element: {
            text: 'Submit',
            tagName: 'button',
            attributes: { id: 'submit-btn', role: 'button' },
            cssClasses: ['btn'],
            dataAttributes: { testid: 'submit' },
            outerHTML: '<button>Submit</button>',
            ancestorPath: 'form > div',
          },
        },
      ],
    };

    const serialized = serializeRecording(session);
    const action = serialized.actions[0];
    const element = action.element;

    // Element should still exist but stripped
    expect(element).toBeDefined();
    expect(element.text).toBe('Submit');
    expect(element.tagName).toBe('button');
    expect(element.attributes).toEqual({ id: 'submit-btn', role: 'button' });
    expect(element.ancestorPath).toBe('form > div');

    // Stripped fields
    expect(element).not.toHaveProperty('cssClasses');
    expect(element).not.toHaveProperty('dataAttributes');
    expect(element).not.toHaveProperty('outerHTML');
  });

  it('should handle extract_variable actions with selectedText', () => {
    /** @type {import('../types.js').RecordingSession} */
    const session = {
      id: 'session-1',
      startedAt: 1000,
      stoppedAt: 2000,
      tabId: 123,
      startingUrl: 'https://example.com',
      actions: [
        {
          id: 'action-1',
          type: 'extract_variable',
          rawAction: {
            type: 'extract_variable',
            timestamp: 1000,
            url: 'https://example.com',
            selectedText: 'Order #12345',
          },
          prompt: 'extract order number',
          promptEdited: false,
          url: 'https://example.com',
          timestamp: 1000,
          isIntent: false,
          assertions: [],
          variableName: 'orderNumber',
          selectedText: 'Order #12345',
        },
      ],
    };

    const serialized = serializeRecording(session);
    const action = serialized.actions[0];

    expect(action.type).toBe('extract_variable');
    expect(action.variableName).toBe('orderNumber');
    expect(action.selectedText).toBe('Order #12345');
    expect(action).not.toHaveProperty('rawAction');
  });
});

describe('serializeActions', () => {
  it('should serialize an array of actions', () => {
    /** @type {import('../types.js').ActionEntry[]} */
    const actions = [
      {
        id: 'action-1',
        type: 'click',
        rawAction: { type: 'click', timestamp: 1000, url: 'https://example.com' },
        prompt: 'click on button',
        promptEdited: false,
        url: 'https://example.com',
        timestamp: 1000,
        isIntent: false,
        assertions: [],
      },
      {
        id: 'action-2',
        type: 'type',
        rawAction: { type: 'type', timestamp: 1001, url: 'https://example.com', value: 'hello' },
        prompt: 'type hello',
        promptEdited: true,
        url: 'https://example.com',
        timestamp: 1001,
        isIntent: false,
        assertions: [],
      },
    ];

    const serialized = serializeActions(actions);

    expect(serialized).toHaveLength(2);
    expect(serialized[0]).not.toHaveProperty('rawAction');
    expect(serialized[0]).not.toHaveProperty('promptEdited');
    expect(serialized[1]).not.toHaveProperty('rawAction');
    expect(serialized[1]).not.toHaveProperty('promptEdited');
  });

  it('should handle null/undefined actions', () => {
    expect(serializeActions(null)).toEqual([]);
    expect(serializeActions(undefined)).toEqual([]);
  });

  it('should handle empty array', () => {
    expect(serializeActions([])).toEqual([]);
  });
});
