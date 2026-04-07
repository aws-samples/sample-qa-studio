// Nova Act Recorder - Prompt Generator Property Tests
// Tests for PromptGenerator: generatePrompt, generateAllPrompts, suggestMergedPrompts.

import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import { PromptGenerator } from '../prompt-generator.js';
import { generateId } from '../session-manager.js';

// ─── Arbitraries ───

const urlArb = fc.webUrl();

const nonEmptyString = fc.string({ minLength: 1, maxLength: 60 })
  .map(s => s.trim())
  .filter(s => s.length > 0);

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

const scrollDirArb = fc.constantFrom('up', 'down');

/** Helper to build an ActionEntry from a RawAction. */
function makeEntry(rawAction, overrides = {}) {
  return {
    id: generateId(),
    type: rawAction.type,
    rawAction,
    prompt: '',
    promptEdited: false,
    url: rawAction.url,
    timestamp: rawAction.timestamp,
    isExtraction: false,
    isIntent: false,
    assertions: [],
    ...overrides,
  };
}

// ─── Task 4.4.1: Property 7 — Prompt format by action type ───

describe('Property 7: Prompt format by action type', () => {
  // Feature: nova-act-recorder, Property 7: Prompt format by action type
  // **Validates: Requirements 6.2, 6.3, 6.4, 6.5, 13.6**

  const pg = new PromptGenerator();

  it('click prompts should contain "click on \'" + element descriptor', () => {
    fc.assert(
      fc.property(
        elementDescriptorArb,
        fc.integer({ min: 1000000000000, max: 2000000000000 }),
        urlArb,
        (element, timestamp, url) => {
          const raw = { type: 'click', timestamp, url, element };
          const entry = makeEntry(raw);
          const prompt = pg.generatePrompt(entry);

          expect(prompt).toContain("click on '");
          expect(prompt).toContain(element.text);
          expect(prompt).toBe(`click on '${element.text}'`);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('typing prompts should contain "type \'" + value + "\' into the \'" + element descriptor', () => {
    fc.assert(
      fc.property(
        elementDescriptorArb,
        nonEmptyString,
        fc.integer({ min: 1000000000000, max: 2000000000000 }),
        urlArb,
        (element, value, timestamp, url) => {
          const raw = { type: 'type', timestamp, url, element, value };
          const entry = makeEntry(raw);
          const prompt = pg.generatePrompt(entry);

          expect(prompt).toContain("type '");
          expect(prompt).toContain(value);
          expect(prompt).toContain("' into the '");
          expect(prompt).toContain(element.text);
          expect(prompt).toBe(`type '${value}' into the '${element.text}' field`);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('scroll prompts should start with "scroll " + direction', () => {
    fc.assert(
      fc.property(
        scrollDirArb,
        fc.integer({ min: 1000000000000, max: 2000000000000 }),
        urlArb,
        (direction, timestamp, url) => {
          const raw = { type: 'scroll', timestamp, url, value: direction };
          const entry = makeEntry(raw);
          const prompt = pg.generatePrompt(entry);

          expect(prompt).toMatch(new RegExp(`^scroll ${direction}`));
          expect(prompt).toBe(`scroll ${direction}`);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('scroll prompts with container should include container descriptor', () => {
    fc.assert(
      fc.property(
        scrollDirArb,
        elementDescriptorArb,
        fc.integer({ min: 1000000000000, max: 2000000000000 }),
        urlArb,
        (direction, container, timestamp, url) => {
          const raw = { type: 'scroll', timestamp, url, value: direction, scrollContainer: container };
          const entry = makeEntry(raw);
          const prompt = pg.generatePrompt(entry);

          expect(prompt).toMatch(new RegExp(`^scroll ${direction}`));
          expect(prompt).toContain(container.text);
          expect(prompt).toBe(`scroll ${direction} in the '${container.text}'`);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('navigation prompts should contain "navigate to \'" + URL', () => {
    fc.assert(
      fc.property(
        urlArb,
        fc.integer({ min: 1000000000000, max: 2000000000000 }),
        (navUrl, timestamp) => {
          const raw = { type: 'navigation', timestamp, url: navUrl, value: navUrl };
          const entry = makeEntry(raw);
          const prompt = pg.generatePrompt(entry);

          expect(prompt).toContain("navigate to '");
          expect(prompt).toContain(navUrl);
          expect(prompt).toBe(`navigate to '${navUrl}'`);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('tab_switch prompts with title should include title and URL', () => {
    fc.assert(
      fc.property(
        nonEmptyString,
        urlArb,
        fc.integer({ min: 1000000000000, max: 2000000000000 }),
        (title, url, timestamp) => {
          const raw = { type: 'tab_switch', timestamp, url, value: url, tabTitle: title };
          const entry = makeEntry(raw);
          const prompt = pg.generatePrompt(entry);

          expect(prompt).toContain(title);
          expect(prompt).toContain(url);
          expect(prompt).toBe(`switch to tab '${title}' (${url})`);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('tab_switch prompts without title should show URL', () => {
    fc.assert(
      fc.property(
        urlArb,
        fc.integer({ min: 1000000000000, max: 2000000000000 }),
        (url, timestamp) => {
          const raw = { type: 'tab_switch', timestamp, url, value: url, tabTitle: '' };
          const entry = makeEntry(raw);
          const prompt = pg.generatePrompt(entry);

          expect(prompt).toContain(url);
          expect(prompt).toBe(`switch to tab at '${url}'`);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('extract_variable with extractionLabel uses the label as prompt', () => {
    fc.assert(
      fc.property(
        elementDescriptorArb,
        nonEmptyString,
        nonEmptyString,
        fc.integer({ min: 1000000000000, max: 2000000000000 }),
        urlArb,
        (element, selectedText, label, timestamp, url) => {
          const raw = { type: 'extract_variable', timestamp, url, element, selectedText, extractionLabel: label };
          const entry = makeEntry(raw);
          const prompt = pg.generatePrompt(entry);

          expect(prompt).toBe(label);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('extract_variable without extractionLabel falls back to element text', () => {
    fc.assert(
      fc.property(
        elementDescriptorArb,
        nonEmptyString,
        fc.integer({ min: 1000000000000, max: 2000000000000 }),
        urlArb,
        (element, selectedText, timestamp, url) => {
          const raw = { type: 'extract_variable', timestamp, url, element, selectedText };
          const entry = makeEntry(raw);
          const prompt = pg.generatePrompt(entry);

          expect(prompt).toBe(`the '${element.text}'`);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('paste prompts should contain "type \'" + value + "\' into the \'" + element descriptor', () => {
    fc.assert(
      fc.property(
        elementDescriptorArb,
        nonEmptyString,
        fc.integer({ min: 1000000000000, max: 2000000000000 }),
        urlArb,
        (element, value, timestamp, url) => {
          const raw = { type: 'paste', timestamp, url, element, value };
          const entry = makeEntry(raw);
          const prompt = pg.generatePrompt(entry);

          expect(prompt).toContain("type '");
          expect(prompt).toContain(value);
          expect(prompt).toContain("' into the '");
          expect(prompt).toContain(element.text);
          expect(prompt).toBe(`type '${value}' into the '${element.text}' field`);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('intent prompts should equal the user-provided text', () => {
    fc.assert(
      fc.property(
        nonEmptyString,
        (intentText) => {
          const entry = {
            id: generateId(),
            type: 'intent',
            prompt: intentText,
            promptEdited: false,
            url: '',
            timestamp: Date.now(),
            isExtraction: false,
            isIntent: true,
            assertions: [],
          };
          const prompt = pg.generatePrompt(entry);

          expect(prompt).toBe(intentText);
        }
      ),
      { numRuns: 100 }
    );
  });
});
