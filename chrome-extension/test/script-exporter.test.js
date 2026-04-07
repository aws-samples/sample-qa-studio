// Nova Act Recorder - Script Exporter Property Tests
// Tests for ScriptExporter: exportScript with regular actions, intents, and assertions.

import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import { ScriptExporter } from '../script-exporter.js';
import { generateId } from '../session-manager.js';

// ─── Arbitraries ───

const urlArb = fc.webUrl();

const nonEmptyString = fc.string({ minLength: 1, maxLength: 60 })
  .map(s => s.trim())
  .filter(s => s.length > 0);

/** Generates strings safe for Python double-quoted strings (no backslashes, quotes, or control chars). */
const safePythonString = fc.stringOf(
  fc.char().filter(c => c !== '"' && c !== '\\' && c !== '\n' && c !== '\r' && c !== '\t' && c.charCodeAt(0) >= 32),
  { minLength: 1, maxLength: 50 }
).filter(s => s.trim().length > 0);

const elementDescriptorArb = fc.record({
  text: safePythonString,
  tagName: fc.constantFrom('button', 'input', 'a', 'div', 'span', 'textarea'),
  attributes: fc.record({
    id: fc.option(safePythonString, { nil: undefined }),
    ariaLabel: fc.option(safePythonString, { nil: undefined }),
  }),
});

const scrollDirArb = fc.constantFrom('up', 'down');

/** Builds a regular click ActionEntry. */
function makeClickAction(element, url) {
  const raw = { type: 'click', timestamp: Date.now(), url, element };
  return {
    id: generateId(),
    type: 'click',
    rawAction: raw,
    prompt: `click on '${element.text}'`,
    promptEdited: false,
    url,
    timestamp: Date.now(),

    isIntent: false,
    assertions: [],
  };
}

/** Builds a regular type ActionEntry. */
function makeTypeAction(element, value, url) {
  const raw = { type: 'type', timestamp: Date.now(), url, element, value };
  return {
    id: generateId(),
    type: 'type',
    rawAction: raw,
    prompt: `type '${value}' into the '${element.text}' field`,
    promptEdited: false,
    url,
    timestamp: Date.now(),

    isIntent: false,
    assertions: [],
  };
}

/** Builds a navigation ActionEntry. */
function makeNavAction(url) {
  const raw = { type: 'navigation', timestamp: Date.now(), url, value: url };
  return {
    id: generateId(),
    type: 'navigation',
    rawAction: raw,
    prompt: `navigate to '${url}'`,
    promptEdited: false,
    url,
    timestamp: Date.now(),

    isIntent: false,
    assertions: [],
  };
}

/** Builds a scroll ActionEntry. */
function makeScrollAction(direction, url) {
  const raw = { type: 'scroll', timestamp: Date.now(), url, value: direction };
  return {
    id: generateId(),
    type: 'scroll',
    rawAction: raw,
    prompt: `scroll ${direction}`,
    promptEdited: false,
    url,
    timestamp: Date.now(),

    isIntent: false,
    assertions: [],
  };
}

/** Builds an intent ActionEntry. */
function makeIntentAction(intentText) {
  return {
    id: generateId(),
    type: 'intent',
    prompt: intentText,
    promptEdited: false,
    url: '',
    timestamp: Date.now(),

    isIntent: true,
    assertions: [],
  };
}

/** Builds an assertion object. */
function makeAssertion(text) {
  return {
    id: generateId(),
    text,
  };
}

/** Arbitrary for a random regular action (click, type, scroll, navigation). */
const regularActionArb = fc.oneof(
  fc.tuple(elementDescriptorArb, urlArb).map(([el, url]) => makeClickAction(el, url)),
  fc.tuple(elementDescriptorArb, safePythonString, urlArb).map(([el, val, url]) => makeTypeAction(el, val, url)),
  fc.tuple(scrollDirArb, urlArb).map(([dir, url]) => makeScrollAction(dir, url)),
  urlArb.map(url => makeNavAction(url))
);

/** Arbitrary for an intent action. */
const intentActionArb = safePythonString.map(text => makeIntentAction(text));

/** Arbitrary for a mixed action (regular or intent). */
const mixedActionArb = fc.oneof(
  { weight: 5, arbitrary: regularActionArb },
  { weight: 2, arbitrary: intentActionArb }
);

/** Arbitrary for an ExportableSession with at least one action. */
const exportableSessionArb = fc.tuple(
  urlArb,
  fc.array(mixedActionArb, { minLength: 1, maxLength: 10 })
).map(([startingUrl, actions]) => ({ startingUrl, actions }));

// ─── Helpers ───

const exporter = new ScriptExporter();

/**
 * Simulates the scroll-merge preprocessing that the exporter performs.
 * Consecutive scrolls collapse to the last one, which merges into the next
 * non-scroll/non-tab_switch/non-navigation action. Trailing scrolls stay standalone.
 */
function simulateScrollMerge(actions) {
  const result = [];
  let pendingScroll = null;
  for (const action of actions) {
    if (action.type === 'scroll') {
      pendingScroll = action;
    } else if (action.type === 'tab_switch' || action.type === 'navigation') {
      if (pendingScroll) { result.push(pendingScroll); pendingScroll = null; }
      result.push(action);
    } else {
      if (pendingScroll) {
        result.push({ ...action, prompt: `${pendingScroll.prompt} and ${action.prompt}` });
        pendingScroll = null;
      } else {
        result.push(action);
      }
    }
  }
  if (pendingScroll) result.push(pendingScroll);
  return result;
}

/**
 * Counts occurrences of a substring in a string.
 */
function countOccurrences(str, sub) {
  let count = 0;
  let pos = 0;
  while ((pos = str.indexOf(sub, pos)) !== -1) {
    count++;
    pos += sub.length;
  }
  return count;
}

/**
 * Validates that the exported script has correct Python structure:
 * - Contains the NovaAct import
 * - Contains at least one with block
 * - Body lines inside the outermost with block are indented at least 4 spaces
 */
function validatePythonStructure(script) {
  const lines = script.split('\n');

  // Must have the NovaAct import
  const hasNovaActImport = lines.some(l => l.trim() === 'from nova_act import NovaAct');
  expect(hasNovaActImport).toBe(true);

  // Must have at least one with block (may be indented for nested multi-tab)
  const withIndices = lines.reduce((acc, l, i) => {
    if (l.trimStart().startsWith('with NovaAct(starting_page=')) acc.push(i);
    return acc;
  }, []);
  expect(withIndices.length).toBeGreaterThanOrEqual(1);

  // Find the outermost with block (first one at column 0)
  const outermostIdx = withIndices.find(i => lines[i].startsWith('with '));
  if (outermostIdx !== undefined) {
    // All non-empty lines after the outermost with should be indented
    for (let i = outermostIdx + 1; i < lines.length; i++) {
      const line = lines[i];
      if (line.trim() === '') continue;
      expect(line.startsWith('    ')).toBe(true);
    }
  }
}

// ─── Task 5.6.1: Property 9 — Export produces valid Python with correct structure ───

describe('Property 9: Export produces valid Python with correct structure', () => {
  // Feature: nova-act-recorder, Property 9: Export produces valid Python with correct structure
  // **Validates: Requirements 8.1, 8.2, 8.3, 8.6**

  it('exported script contains NovaAct import, context manager, and correct number of act/act_get calls', () => {
    fc.assert(
      fc.property(exportableSessionArb, (session) => {
        const script = exporter.exportScript(session);

        // (a) Validate Python structure
        validatePythonStructure(script);

        // (b) Contains from nova_act import NovaAct
        expect(script).toContain('from nova_act import NovaAct');

        // (c) Contains with NovaAct(starting_page="...") as nova...:
        expect(script).toContain(`with NovaAct(starting_page="`);

        // (d) Count act() and act_get() calls
        // The exporter skips the first navigation action (used as starting_page),
        // merges consecutive scrolls into the next action, and consumes tab_switch actions
        let actionsAfterNav = (session.actions.length > 0 && session.actions[0].type === 'navigation')
          ? session.actions.slice(1)
          : session.actions;
        // Simulate scroll merging (matches exporter behavior)
        actionsAfterNav = simulateScrollMerge(actionsAfterNav);
        // tab_switch and navigations absorbed as starting_page for subsequent segments don't produce act() calls
        // Intent actions produce act_get (not act), so they are counted separately
        let expectedActCalls = 0;
        let expectedIntentActGetCalls = 0;
        let skipNext = false;
        for (const a of actionsAfterNav) {
          if (a.type === 'tab_switch') { skipNext = true; continue; }
          if (skipNext && a.type === 'navigation') { skipNext = false; continue; }
          skipNext = false;
          if (a.isIntent) {
            expectedIntentActGetCalls++;
          } else {
            expectedActCalls++;
          }
        }
        // act_get calls come from assertions on non-tab_switch/non-intent actions, plus intent actions
        const expectedAssertionActGetCalls = actionsAfterNav
          .filter(a => a.type !== 'tab_switch' && !a.isIntent)
          .reduce((sum, a) => sum + (a.assertions ? a.assertions.length : 0), 0);

        // Count all .act( and .act_get( calls (handles nova, nova_1, nova_2, etc.)
        const actCallCount = (script.match(/\.act\((?!_get)/g) || []).length;
        const actGetCallCount = (script.match(/\.act_get\(/g) || []).length;

        expect(actCallCount).toBe(expectedActCalls);
        expect(actGetCallCount).toBe(expectedAssertionActGetCalls + expectedIntentActGetCalls);
      }),
      { numRuns: 100 }
    );
  });

  it('empty action log produces a script with pass statement', () => {
    const session = { startingUrl: 'https://example.com', actions: [] };
    const script = exporter.exportScript(session);

    expect(script).toContain('from nova_act import NovaAct');
    expect(script).toContain('with NovaAct(starting_page="https://example.com") as nova:');
    expect(script).toContain('    pass');
  });

  it('starting URL is included in the context manager', () => {
    fc.assert(
      fc.property(exportableSessionArb, (session) => {
        const script = exporter.exportScript(session);
        // The exporter uses the first navigation action's URL if available
        let expectedUrl = session.startingUrl || '';
        if (session.actions.length > 0 && session.actions[0].type === 'navigation') {
          const navUrl = session.actions[0].rawAction ? session.actions[0].rawAction.value : session.actions[0].url;
          if (navUrl) expectedUrl = navUrl;
        }
        const escapedUrl = expectedUrl
          .replace(/\\/g, '\\\\')
          .replace(/"/g, '\\"');
        expect(script).toContain(`starting_page="${escapedUrl}"`);
      }),
      { numRuns: 100 }
    );
  });
});

// ─── Task 5.6.3: Property 19 — Assertion export format and ordering ───

describe('Property 19: Assertion export format and ordering', () => {
  // Feature: nova-act-recorder, Property 19: Assertion export format and ordering
  // **Validates: Requirements 14.10, 14.11**

  it('actions with assertions generate act_get()+assert pairs after the act() call', () => {
    fc.assert(
      fc.property(
        urlArb,
        fc.array(
          fc.tuple(
            regularActionArb,
            fc.array(safePythonString.map(text => makeAssertion(text)), { minLength: 1, maxLength: 3 })
          ),
          { minLength: 1, maxLength: 5 }
        ),
        (startingUrl, actionAssertionPairs) => {
          const actions = actionAssertionPairs.map(([action, assertions]) => ({
            ...action,
            assertions,
          }));
          const session = { startingUrl, actions };
          const script = exporter.exportScript(session);
          const lines = script.split('\n');

          // The exporter skips the first navigation action and merges scrolls
          let exportedActions = (actions.length > 0 && actions[0].type === 'navigation')
            ? actions.slice(1)
            : actions;
          exportedActions = simulateScrollMerge(exportedActions);

          // Total assertions across exported (merged) actions
          const totalAssertions = exportedActions.reduce((sum, a) => sum + a.assertions.length, 0);

          // Count act_get calls (should equal total assertions)
          const actGetCount = (script.match(/\.act_get\(/g) || []).length;
          expect(actGetCount).toBe(totalAssertions);

          // Count assert statements
          const assertCount = countOccurrences(script, 'assert result.parsed_response,');
          expect(assertCount).toBe(totalAssertions);

          // Each assertion act_get should use BOOL_SCHEMA
          const actGetLines = lines.filter(l => l.includes('.act_get('));
          for (const line of actGetLines) {
            expect(line).toContain('schema=BOOL_SCHEMA');
          }

          // Verify ordering: for each exported non-scroll action, act() comes before its assertion act_get()+assert
          for (const action of exportedActions) {
            if (action.type === 'scroll') continue;
            const promptEscaped = action.prompt
              .replace(/\\/g, '\\\\')
              .replace(/"/g, '\\"');
            const actLineIdx = lines.findIndex(l => l.includes(`.act("${promptEscaped}")`));
            expect(actLineIdx).toBeGreaterThanOrEqual(0);

            for (const assertion of action.assertions) {
              const assertionEscaped = assertion.text
                .replace(/\\/g, '\\\\')
                .replace(/"/g, '\\"');
              const assertGetIdx = lines.findIndex(
                (l, idx) => idx > actLineIdx && l.includes(`.act_get("${assertionEscaped}"`)
              );
              expect(assertGetIdx).toBeGreaterThan(actLineIdx);

              // The assert statement should follow the act_get
              const assertStmtIdx = lines.findIndex(
                (l, idx) => idx > assertGetIdx && l.includes(`assert result.parsed_response, "${assertionEscaped}"`)
              );
              expect(assertStmtIdx).toBe(assertGetIdx + 1);
            }
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('BOOL_SCHEMA is imported when assertions are present', () => {
    const action = makeClickAction(
      { text: 'Submit', tagName: 'button', attributes: {} },
      'https://example.com'
    );
    action.assertions = [makeAssertion('success message is visible')];
    const session = { startingUrl: 'https://example.com', actions: [action] };
    const script = exporter.exportScript(session);

    expect(script).toContain('from nova_act import BOOL_SCHEMA');
  });

  it('actions without assertions do not generate act_get or assert lines', () => {
    const action = makeClickAction(
      { text: 'Submit', tagName: 'button', attributes: {} },
      'https://example.com'
    );
    const session = { startingUrl: 'https://example.com', actions: [action] };
    const script = exporter.exportScript(session);

    expect(script).not.toContain('.act_get(');
    expect(script).not.toContain('assert result.parsed_response');
  });
});

// ─── Multi-tab export ───

/** Builds a tab_switch ActionEntry. */
function makeTabSwitchAction(url, tabTitle, tabId) {
  const raw = { type: 'tab_switch', timestamp: Date.now(), url, value: url, tabTitle: tabTitle || '', tabId };
  return {
    id: generateId(),
    type: 'tab_switch',
    rawAction: raw,
    prompt: tabTitle ? `switch to tab '${tabTitle}' (${url})` : `switch to tab at '${url}'`,
    promptEdited: false,
    url,
    timestamp: Date.now(),
    isIntent: false,
    assertions: [],
  };
}

/** Builds an extract_variable ActionEntry. */
function makeExtractAction(element, url, variableName) {
  const raw = { type: 'extract_variable', timestamp: Date.now(), url, element, selectedText: 'some text' };
  return {
    id: generateId(),
    type: 'extract_variable',
    rawAction: raw,
    prompt: `the '${element.text}'`,
    promptEdited: false,
    url,
    timestamp: Date.now(),
    isIntent: false,
    assertions: [],
    variableName,
    selectedText: 'some text',
  };
}

/** Builds a paste ActionEntry with optional sourceVariableName. */
function makePasteAction(element, value, url, sourceVariableName) {
  const raw = { type: 'paste', timestamp: Date.now(), url, element, value };
  const entry = {
    id: generateId(),
    type: 'paste',
    rawAction: raw,
    prompt: `type '${value}' into the '${element.text}' field`,
    promptEdited: false,
    url,
    timestamp: Date.now(),
    isIntent: false,
    assertions: [],
  };
  if (sourceVariableName) {
    entry.sourceVariableName = sourceVariableName;
  }
  return entry;
}

describe('Multi-tab export generates nested with blocks', () => {
  it('single-tab session uses "nova" as variable name', () => {
    const click = makeClickAction(
      { text: 'Submit', tagName: 'button', attributes: {} },
      'https://example.com'
    );
    const session = { startingUrl: 'https://example.com', actions: [click] };
    const script = exporter.exportScript(session);

    expect(script).toContain('as nova:');
    expect(script).not.toContain('as nova_1:');
  });

  it('multi-tab session generates nested with blocks with nova_1/nova_2', () => {
    const click1 = makeClickAction(
      { text: 'Login', tagName: 'button', attributes: {} },
      'https://site-a.com'
    );
    const tabSwitch = makeTabSwitchAction('https://site-b.com', 'Site B', 2);
    const nav = makeNavAction('https://site-b.com/page');
    const click2 = makeClickAction(
      { text: 'Signup', tagName: 'button', attributes: {} },
      'https://site-b.com/page'
    );

    const session = {
      startingUrl: 'https://site-a.com',
      startingTabId: 1,
      actions: [click1, tabSwitch, nav, click2],
    };
    const script = exporter.exportScript(session);

    expect(script).toContain('as nova_1:');
    expect(script).toContain('as nova_2:');
    // Tab switch should not produce an act() call
    expect(script).not.toContain('switch to');
    // Navigation after tab_switch is absorbed as starting_page
    expect(script).toContain('starting_page="https://site-b.com/page"');
    // All actions at innermost depth (8 spaces for 2 tabs)
    const lines = script.split('\n');
    const click1Line = lines.find(l => l.includes("click on 'Login'"));
    const click2Line = lines.find(l => l.includes("click on 'Signup'"));
    expect(click1Line).toMatch(/^        nova_1\.act/);
    expect(click2Line).toMatch(/^        nova_2\.act/);
  });

  it('switching back to original tab reuses nova_1 (no duplicate NovaAct)', () => {
    const click1 = makeClickAction(
      { text: 'Search', tagName: 'button', attributes: {} },
      'https://site-a.com'
    );
    const switchToB = makeTabSwitchAction('https://site-b.com', 'Site B', 2);
    const click2 = makeClickAction(
      { text: 'Copy', tagName: 'button', attributes: {} },
      'https://site-b.com'
    );
    const switchBackToA = makeTabSwitchAction('https://site-a.com/dashboard', 'Site A', 1);
    const click3 = makeClickAction(
      { text: 'Paste', tagName: 'button', attributes: {} },
      'https://site-a.com/dashboard'
    );

    const session = {
      startingUrl: 'https://site-a.com',
      startingTabId: 1,
      actions: [click1, switchToB, click2, switchBackToA, click3],
    };
    const script = exporter.exportScript(session);

    // Structure: all with blocks at top, all actions at innermost depth
    // with NovaAct(...) as nova_1:
    //     with NovaAct(...) as nova_2:
    //         nova_1.act("click on 'Search'")
    //         nova_2.act("click on 'Copy'")
    //         nova_1.act("click on 'Paste'")
    expect(script).toContain('as nova_1:');
    expect(script).toContain('as nova_2:');
    expect(script).not.toContain('nova_3');

    // Only 2 with blocks total
    const withCount = (script.match(/with NovaAct\(/g) || []).length;
    expect(withCount).toBe(2);

    // All actions at 8-space indent (innermost of 2 tabs)
    const lines = script.split('\n');
    const click1Line = lines.find(l => l.includes("click on 'Search'"));
    const click2Line = lines.find(l => l.includes("click on 'Copy'"));
    const click3Line = lines.find(l => l.includes("click on 'Paste'"));
    expect(click1Line).toMatch(/^        nova_1\.act/);
    expect(click2Line).toMatch(/^        nova_2\.act/);
    expect(click3Line).toMatch(/^        nova_1\.act/);
  });

  it('A → B → C → A produces correct nesting with all tabs at top', () => {
    const click1 = makeClickAction({ text: 'A1', tagName: 'button', attributes: {} }, 'https://a.com');
    const switchToB = makeTabSwitchAction('https://b.com', '', 2);
    const click2 = makeClickAction({ text: 'B1', tagName: 'button', attributes: {} }, 'https://b.com');
    const switchToC = makeTabSwitchAction('https://c.com', '', 3);
    const click3 = makeClickAction({ text: 'C1', tagName: 'button', attributes: {} }, 'https://c.com');
    const switchBackToA = makeTabSwitchAction('https://a.com', '', 1);
    const click4 = makeClickAction({ text: 'A2', tagName: 'button', attributes: {} }, 'https://a.com');

    const session = {
      startingUrl: 'https://a.com',
      startingTabId: 1,
      actions: [click1, switchToB, click2, switchToC, click3, switchBackToA, click4],
    };
    const script = exporter.exportScript(session);

    // Structure: 3 nested with blocks, all actions at 12-space indent
    // with NovaAct("a.com") as nova_1:
    //     with NovaAct("b.com") as nova_2:
    //         with NovaAct("c.com") as nova_3:
    //             nova_1.act("A1")
    //             nova_2.act("B1")
    //             nova_3.act("C1")
    //             nova_1.act("A2")
    const withCount = (script.match(/with NovaAct\(/g) || []).length;
    expect(withCount).toBe(3);

    const lines = script.split('\n');
    const a1 = lines.find(l => l.includes("'A1'"));
    const b1 = lines.find(l => l.includes("'B1'"));
    const c1 = lines.find(l => l.includes("'C1'"));
    const a2 = lines.find(l => l.includes("'A2'"));
    expect(a1).toMatch(/^            nova_1/);   // depth 3 (12 spaces)
    expect(b1).toMatch(/^            nova_2/);   // depth 3
    expect(c1).toMatch(/^            nova_3/);   // depth 3
    expect(a2).toMatch(/^            nova_1/);   // depth 3
  });
});

describe('Paste export with variable references', () => {
  it('paste with sourceVariableName exports f-string', () => {
    const el = { text: 'Name field', tagName: 'input', attributes: {} };
    const paste = makePasteAction(el, 'copied text', 'https://example.com', 'var_1');
    const session = { startingUrl: 'https://example.com', actions: [paste] };
    const script = exporter.exportScript(session);

    expect(script).toContain("nova.act(f\"type '{var_1}' into the 'Name field' field\")");
  });

  it('paste without sourceVariableName exports regular act() call', () => {
    const el = { text: 'Name field', tagName: 'input', attributes: {} };
    const paste = makePasteAction(el, 'some text', 'https://example.com');
    const session = { startingUrl: 'https://example.com', actions: [paste] };
    const script = exporter.exportScript(session);

    expect(script).toContain("nova.act(\"type 'some text' into the 'Name field' field\")");
    expect(script).not.toContain('f"');
  });

  it('extract + paste in multi-tab uses correct nova var', () => {
    const el = { text: 'Price', tagName: 'span', attributes: {} };
    const extract = makeExtractAction(el, 'https://a.com', 'var_1');
    const tabSwitch = makeTabSwitchAction('https://b.com', 'Tab B');
    const inputEl = { text: 'Amount', tagName: 'input', attributes: {} };
    const paste = makePasteAction(inputEl, '$9.99', 'https://b.com', 'var_1');

    const session = {
      startingUrl: 'https://a.com',
      actions: [extract, tabSwitch, paste],
    };
    const script = exporter.exportScript(session);

    // extract is in nova_1, paste is in nova_2 — both at innermost depth (8 spaces)
    const lines = script.split('\n');
    const extractLine = lines.find(l => l.includes('var_1 = nova_1.act_get('));
    const pasteLine = lines.find(l => l.includes("nova_2.act(f\"type '{var_1}'"));
    expect(extractLine).toMatch(/^        var_1 = nova_1\.act_get\(/);
    expect(pasteLine).toMatch(/^        nova_2\.act\(/);
  });
});

describe('Extract variable with extractionLabel', () => {
  it('extract with extractionLabel uses the label in act_get prompt', () => {
    const el = { text: '13.7 yrs / 3 days', tagName: 'span', attributes: {} };
    const raw = { type: 'extract_variable', timestamp: Date.now(), url: 'https://example.com', element: el, selectedText: '13.7 yrs', extractionLabel: 'Transit Time' };
    const extract = {
      id: generateId(),
      type: 'extract_variable',
      rawAction: raw,
      prompt: 'Transit Time',
      promptEdited: false,
      url: 'https://example.com',
      timestamp: Date.now(),
      isIntent: false,
      assertions: [],
      variableName: 'var_1',
      selectedText: '13.7 yrs',
    };
    const session = { startingUrl: 'https://example.com', actions: [extract] };
    const script = exporter.exportScript(session);

    expect(script).toContain('var_1 = nova.act_get("Transit Time", schema=STRING_SCHEMA)');
    expect(script).not.toContain('13.7 yrs');
  });

  it('extract without extractionLabel falls back to element descriptor', () => {
    const el = { text: '13.7 yrs / 3 days', tagName: 'span', attributes: {} };
    const extract = makeExtractAction(el, 'https://example.com', 'var_1');
    const session = { startingUrl: 'https://example.com', actions: [extract] };
    const script = exporter.exportScript(session);

    expect(script).toContain("var_1 = nova.act_get(\"the '13.7 yrs / 3 days'\", schema=STRING_SCHEMA)");
  });
});
