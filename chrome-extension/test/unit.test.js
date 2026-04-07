// Nova Act Recorder - Unit Tests
// Tests for specific edge cases, export behavior, and integration points.

import { describe, it, expect } from 'vitest';
import { ScriptExporter } from '../script-exporter.js';
import { PromptGenerator } from '../prompt-generator.js';
import { ActionStore } from '../action-store.js';
import { SessionManager } from '../session-manager.js';
import { extractElementDescriptor, consolidateTyping } from '../element-descriptor.js';

// ─── Helpers ───

function makeRawAction(type, opts = {}) {
  return {
    type,
    timestamp: Date.now(),
    url: opts.url || 'https://example.com',
    element: opts.element || { text: 'Button', tagName: 'button', attributes: {} },
    value: opts.value,
    scrollContainer: opts.scrollContainer,
  };
}

function makeActionEntry(type, prompt, opts = {}) {
  return {
    id: crypto.randomUUID(),
    type,
    rawAction: opts.rawAction || makeRawAction(type, opts),
    prompt,
    promptEdited: false,
    url: opts.url || 'https://example.com',
    timestamp: Date.now(),
    isIntent: opts.isIntent || false,
    collapsedActions: opts.collapsedActions,
    assertions: opts.assertions || [],
  };
}

// ─── ScriptExporter Unit Tests ───

describe('ScriptExporter - edge cases', () => {
  const exporter = new ScriptExporter();

  it('empty session produces pass statement', () => {
    const script = exporter.exportScript({ startingUrl: 'https://example.com', actions: [] });
    expect(script).toContain('starting_page="https://example.com"');
    expect(script).toContain('    pass');
    expect(script).not.toContain('nova.act(');
  });

  it('first navigation action becomes starting_page and is skipped from act() calls', () => {
    const nav = makeActionEntry('navigation', "navigate to 'https://example.com'", {
      rawAction: { type: 'navigation', timestamp: Date.now(), url: 'https://example.com', value: 'https://example.com' },
    });
    const click = makeActionEntry('click', "click on 'Submit'");
    const script = exporter.exportScript({ startingUrl: '', actions: [nav, click] });

    expect(script).toContain('starting_page="https://example.com"');
    expect(script).not.toContain("nova.act(\"navigate to");
    expect(script).toContain("nova.act(\"click on 'Submit'\")");
  });

  it('escapes quotes in prompts', () => {
    const action = makeActionEntry('click', 'click on "Submit" button');
    const script = exporter.exportScript({ startingUrl: 'https://example.com', actions: [action] });
    expect(script).toContain('click on \\"Submit\\" button');
  });

  it('assertions generate act_get + assert pairs after the action', () => {
    const action = makeActionEntry('click', "click on 'Submit'", {
      assertions: [
        { id: '1', text: 'success message visible' },
        { id: '2', text: 'error not shown' },
      ],
    });
    const script = exporter.exportScript({ startingUrl: 'https://example.com', actions: [action] });
    const lines = script.split('\n');

    const actLine = lines.findIndex(l => l.includes("nova.act(\"click on"));
    const assert1 = lines.findIndex(l => l.includes('success message visible'));
    const assert2 = lines.findIndex(l => l.includes('error not shown'));

    expect(actLine).toBeGreaterThan(0);
    expect(assert1).toBeGreaterThan(actLine);
    expect(assert2).toBeGreaterThan(assert1);
  });
});

// ─── PromptGenerator Unit Tests ───

describe('PromptGenerator - specific formats', () => {
  const pg = new PromptGenerator();

  it('click prompt format', () => {
    const entry = makeActionEntry('click', '', {
      rawAction: makeRawAction('click', { element: { text: 'Add to Cart', tagName: 'button', attributes: {} } }),
    });
    expect(pg.generatePrompt(entry)).toBe("click on 'Add to Cart'");
  });

  it('type prompt format', () => {
    const entry = makeActionEntry('type', '', {
      rawAction: makeRawAction('type', {
        element: { text: 'Search', tagName: 'input', attributes: {} },
        value: 'coffee maker',
      }),
    });
    expect(pg.generatePrompt(entry)).toBe("type 'coffee maker' into the 'Search' field");
  });

  it('scroll prompt without container', () => {
    const entry = makeActionEntry('scroll', '', {
      rawAction: makeRawAction('scroll', { value: 'down' }),
    });
    expect(pg.generatePrompt(entry)).toBe('scroll down');
  });

  it('scroll prompt with container', () => {
    const entry = makeActionEntry('scroll', '', {
      rawAction: makeRawAction('scroll', {
        value: 'up',
        scrollContainer: { text: 'Product List', tagName: 'div', attributes: {} },
      }),
    });
    expect(pg.generatePrompt(entry)).toBe("scroll up in the 'Product List'");
  });

  it('navigation prompt format', () => {
    const entry = makeActionEntry('navigation', '', {
      rawAction: makeRawAction('navigation', { value: 'https://example.com/page' }),
    });
    expect(pg.generatePrompt(entry)).toBe("navigate to 'https://example.com/page'");
  });

  it('intent prompt returns text as-is', () => {
    const entry = { ...makeActionEntry('intent', 'log in with test credentials'), isIntent: true };
    expect(pg.generatePrompt(entry)).toBe('log in with test credentials');
  });
});

// ─── PromptGenerator - merge suggestions ───

describe('PromptGenerator - merge suggestions', () => {
  const pg = new PromptGenerator();

  it('detects type + click search pattern', () => {
    const type = makeActionEntry('type', "type 'coffee' into the 'Search' field", {
      rawAction: makeRawAction('type', {
        element: { text: 'Search', tagName: 'input', attributes: {} },
        value: 'coffee',
      }),
    });
    const click = makeActionEntry('click', "click on 'Search'", {
      rawAction: makeRawAction('click', {
        element: { text: 'Search', tagName: 'button', attributes: {} },
      }),
    });
    const suggestions = pg.suggestMergedPrompts([type, click]);
    expect(suggestions.length).toBe(1);
    expect(suggestions[0].mergedPrompt).toBe("search for 'coffee'");
  });

  it('detects type + click submit pattern', () => {
    const type = makeActionEntry('type', "type 'hello' into the 'Name' field", {
      rawAction: makeRawAction('type', {
        element: { text: 'Name', tagName: 'input', attributes: {} },
        value: 'hello',
      }),
    });
    const click = makeActionEntry('click', "click on 'Submit'", {
      rawAction: makeRawAction('click', {
        element: { text: 'Submit', tagName: 'button', attributes: {} },
      }),
    });
    const suggestions = pg.suggestMergedPrompts([type, click]);
    expect(suggestions.length).toBe(1);
    expect(suggestions[0].mergedPrompt).toContain('submit');
  });

  it('returns empty for non-mergeable actions', () => {
    const click1 = makeActionEntry('click', "click on 'A'");
    const click2 = makeActionEntry('click', "click on 'B'");
    expect(pg.suggestMergedPrompts([click1, click2])).toEqual([]);
  });
});

// ─── ActionStore Unit Tests ───

describe('ActionStore - scroll consolidation edge cases', () => {
  it('single scroll produces one action', () => {
    const store = new ActionStore();
    store.addAction(makeRawAction('scroll', { value: 'down' }));
    expect(store.getActions().length).toBe(1);
  });

  it('scroll then click then scroll produces 3 actions', () => {
    const store = new ActionStore();
    store.addAction(makeRawAction('scroll', { value: 'down' }));
    store.addAction(makeRawAction('click'));
    store.addAction(makeRawAction('scroll', { value: 'down' }));
    expect(store.getActions().length).toBe(3);
  });

  it('10 same-direction scrolls produce 1 action', () => {
    const store = new ActionStore();
    for (let i = 0; i < 10; i++) {
      store.addAction(makeRawAction('scroll', { value: 'up' }));
    }
    expect(store.getActions().length).toBe(1);
  });
});

// ─── SessionManager Unit Tests ───

describe('SessionManager - lifecycle', () => {
  it('starts and stops recording correctly', () => {
    const sm = new SessionManager();
    expect(sm.isRecording()).toBe(false);

    sm.startRecording(1, 'https://example.com');
    expect(sm.isRecording()).toBe(true);
    expect(sm.getActiveTabId()).toBe(1);

    const session = sm.stopRecording();
    expect(sm.isRecording()).toBe(false);
    expect(session).not.toBeNull();
    expect(session.startingUrl).toBe('https://example.com');
  });

  it('handleTabClosed stops recording for the right tab', () => {
    const sm = new SessionManager();
    sm.startRecording(42, 'https://example.com');

    // Wrong tab — no effect
    expect(sm.handleTabClosed(99)).toBeNull();
    expect(sm.isRecording()).toBe(true);

    // Right tab — stops
    const session = sm.handleTabClosed(42);
    expect(session).not.toBeNull();
    expect(sm.isRecording()).toBe(false);
  });

  it('recording follows tab switch', () => {
    const sm = new SessionManager();
    sm.startRecording(1, 'https://example.com');

    expect(sm.isPaused()).toBe(false);
    sm.handleTabActivated(2);
    expect(sm.isPaused()).toBe(false);
    expect(sm.getActiveTabId()).toBe(2);
    expect(sm.shouldCaptureAction(2)).toBe(true);
    expect(sm.shouldCaptureAction(1)).toBe(false);

    sm.handleTabActivated(1);
    expect(sm.isPaused()).toBe(false);
    expect(sm.getActiveTabId()).toBe(1);
    expect(sm.shouldCaptureAction(1)).toBe(true);
  });
});

// ─── ElementDescriptor Unit Tests ───

describe('ElementDescriptor - specific elements', () => {
  function mockEl(opts = {}) {
    const attrMap = {};
    if (opts.ariaLabel) attrMap['aria-label'] = opts.ariaLabel;
    if (opts.role) attrMap['role'] = opts.role;
    if (opts.placeholder) attrMap['placeholder'] = opts.placeholder;
    if (opts.name) attrMap['name'] = opts.name;
    if (opts.type) attrMap['type'] = opts.type;
    return {
      tagName: (opts.tagName || 'DIV').toUpperCase(),
      textContent: opts.textContent || '',
      id: opts.id || '',
      isContentEditable: false,
      getAttribute: (attr) => attrMap[attr] || null,
      parentElement: null,
    };
  }

  it('button with text uses text', () => {
    const el = mockEl({ tagName: 'button', textContent: 'Submit' });
    expect(extractElementDescriptor(el).text).toBe('Submit');
  });

  it('input with placeholder uses placeholder', () => {
    const el = mockEl({ tagName: 'input', placeholder: 'Search...' });
    expect(extractElementDescriptor(el).text).toBe('Search...');
  });

  it('div with aria-label uses aria-label', () => {
    const el = mockEl({ tagName: 'div', ariaLabel: 'Close dialog' });
    expect(extractElementDescriptor(el).text).toBe('Close dialog');
  });

  it('element with only id uses id', () => {
    const el = mockEl({ tagName: 'div', id: 'main-content' });
    expect(extractElementDescriptor(el).text).toBe('main-content');
  });

  it('element with nothing falls back to tagName:nth-child', () => {
    const el = mockEl({ tagName: 'span' });
    expect(extractElementDescriptor(el).text).toMatch(/^span:nth-child\(\d+\)$/);
  });
});

// ─── Typing Consolidation Unit Tests ───

describe('consolidateTyping - edge cases', () => {
  it('returns empty for null/undefined', () => {
    expect(consolidateTyping(null)).toBe('');
    expect(consolidateTyping(undefined)).toBe('');
  });

  it('returns empty for empty array', () => {
    expect(consolidateTyping([])).toBe('');
  });

  it('returns the only value for single entry', () => {
    expect(consolidateTyping(['hello'])).toBe('hello');
  });

  it('returns last value for multiple entries', () => {
    expect(consolidateTyping(['h', 'he', 'hel', 'hello'])).toBe('hello');
  });
});

// ─── ActionStore - intent and extraction ───

describe('ActionStore - intent operations', () => {
  it('addIntentPrompt inserts at correct position', () => {
    const store = new ActionStore();
    store.addAction(makeRawAction('click'));
    store.addAction(makeRawAction('click'));
    store.addIntentPrompt(1, 'do something');

    const actions = store.getActions();
    expect(actions.length).toBe(3);
    expect(actions[1].isIntent).toBe(true);
    expect(actions[1].prompt).toBe('do something');
  });

  it('collapseToIntent and expandIntent round-trip', () => {
    const store = new ActionStore();
    store.addAction(makeRawAction('click'));
    store.addAction(makeRawAction('click'));
    store.addAction(makeRawAction('click'));
    const originalIds = store.getActions().map(a => a.id);

    store.collapseToIntent(0, 1, 'do two things');
    expect(store.getActions().length).toBe(2);
    expect(store.getActions()[0].isIntent).toBe(true);

    store.expandIntent(0);
    expect(store.getActions().length).toBe(3);
    expect(store.getActions().map(a => a.id)).toEqual(originalIds);
  });
});
