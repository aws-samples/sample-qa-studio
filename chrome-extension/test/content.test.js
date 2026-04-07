import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import { extractElementDescriptor, consolidateTyping } from '../element-descriptor.js';

// ─── Helpers: Mock DOM Element Factory ───

/**
 * Creates a minimal mock DOM element with the given attributes.
 * Simulates the subset of the DOM API used by extractElementDescriptor.
 */
function createMockElement({
  tagName = 'DIV',
  textContent = '',
  ariaLabel = null,
  role = null,
  placeholder = null,
  name = null,
  id = '',
  type = null,
  parentElement = null,
  isContentEditable = false,
} = {}) {
  const attrMap = {};
  if (ariaLabel !== null) attrMap['aria-label'] = ariaLabel;
  if (role !== null) attrMap['role'] = role;
  if (placeholder !== null) attrMap['placeholder'] = placeholder;
  if (name !== null) attrMap['name'] = name;
  if (type !== null) attrMap['type'] = type;

  const el = {
    tagName: tagName.toUpperCase(),
    textContent,
    id: id || '',
    isContentEditable,
    getAttribute(attr) {
      return attrMap[attr] || null;
    },
    parentElement: parentElement || null,
  };

  return el;
}

/**
 * Creates a parent element with multiple children for nth-child testing.
 */
function createParentWithChildren(childTagNames) {
  const children = [];
  const parent = { children, tagName: 'DIV' };

  for (const tag of childTagNames) {
    const child = createMockElement({ tagName: tag, parentElement: parent });
    children.push(child);
  }

  return { parent, children };
}

// ─── Arbitraries ───

/** Generates a non-empty trimmed string (for attribute values). */
const nonEmptyTrimmedString = fc.string({ minLength: 1, maxLength: 40 })
  .map(s => s.trim())
  .filter(s => s.length > 0);

/** Generates an optional non-empty string or null. */
const optionalString = fc.oneof(fc.constant(null), nonEmptyTrimmedString);

/** Generates a valid HTML tag name. */
const tagNameArb = fc.constantFrom('div', 'span', 'button', 'a', 'input', 'textarea', 'select', 'p', 'h1', 'section', 'li');

/** Generates a mock element attribute set with random subsets of attributes. */
const elementAttrsArb = fc.record({
  tagName: tagNameArb,
  textContent: optionalString,
  ariaLabel: optionalString,
  role: optionalString,
  placeholder: optionalString,
  name: optionalString,
  id: optionalString,
});

// ─── Task 2.8.1: Property 2 — Element Descriptor Priority Resolution ───

describe('Property 2: Element descriptor priority resolution', () => {
  // Feature: nova-act-recorder, Property 2: Element descriptor priority resolution
  // **Validates: Requirements 2.2, 2.3**

  it('should select the highest-priority non-empty attribute as the descriptor text', () => {
    fc.assert(
      fc.property(elementAttrsArb, (attrs) => {
        const isInputLike = ['input', 'textarea', 'select'].includes(attrs.tagName);
        const el = createMockElement(attrs);
        const descriptor = extractElementDescriptor(el);

        // Determine expected priority
        const visibleText = isInputLike ? '' : (attrs.textContent || '').replace(/\s+/g, ' ').trim();

        if (visibleText) {
          // Priority 1: visible text (max 80 chars)
          expect(descriptor.text).toBe(visibleText.substring(0, 80));
        } else if (attrs.ariaLabel) {
          // Priority 2: aria-label
          expect(descriptor.text).toBe(attrs.ariaLabel);
        } else if (attrs.role) {
          // Priority 3: role + position
          expect(descriptor.text).toContain(attrs.role);
          expect(descriptor.text).toMatch(/\(\d+\)$/);
        } else if (attrs.placeholder) {
          // Priority 4: placeholder
          expect(descriptor.text).toBe(attrs.placeholder);
        } else if (attrs.name) {
          // Priority 5: name
          expect(descriptor.text).toBe(attrs.name);
        } else if (attrs.id) {
          // Priority 6: id
          expect(descriptor.text).toBe(attrs.id);
        } else {
          // Priority 7: tagName + nth-child position
          expect(descriptor.text).toMatch(new RegExp(`^${attrs.tagName}:nth-child\\(\\d+\\)$`));
        }

        // tagName should always be lowercase
        expect(descriptor.tagName).toBe(attrs.tagName);
      }),
      { numRuns: 100 }
    );
  });

  it('should always return a non-empty text field', () => {
    fc.assert(
      fc.property(elementAttrsArb, (attrs) => {
        const el = createMockElement(attrs);
        const descriptor = extractElementDescriptor(el);
        expect(descriptor.text).toBeTruthy();
        expect(descriptor.text.length).toBeGreaterThan(0);
      }),
      { numRuns: 100 }
    );
  });

  it('should truncate visible text to 80 characters', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 81, maxLength: 200 }).filter(s => s.replace(/\s+/g, ' ').trim().length > 80),
        (longText) => {
          const el = createMockElement({ tagName: 'button', textContent: longText });
          const descriptor = extractElementDescriptor(el);
          expect(descriptor.text.length).toBeLessThanOrEqual(80);
          expect(descriptor.text).toBe(longText.replace(/\s+/g, ' ').trim().substring(0, 80));
        }
      ),
      { numRuns: 100 }
    );
  });

  it('should prefer visible text over aria-label when both present', () => {
    fc.assert(
      fc.property(nonEmptyTrimmedString, nonEmptyTrimmedString, (text, ariaLabel) => {
        const el = createMockElement({ tagName: 'button', textContent: text, ariaLabel });
        const descriptor = extractElementDescriptor(el);
        expect(descriptor.text).toBe(text.replace(/\s+/g, ' ').trim().substring(0, 80));
      }),
      { numRuns: 100 }
    );
  });

  it('should prefer aria-label over role when text is absent', () => {
    fc.assert(
      fc.property(nonEmptyTrimmedString, nonEmptyTrimmedString, (ariaLabel, role) => {
        const el = createMockElement({ tagName: 'div', ariaLabel, role });
        const descriptor = extractElementDescriptor(el);
        expect(descriptor.text).toBe(ariaLabel);
      }),
      { numRuns: 100 }
    );
  });

  it('should use tagName + nth-child when no attributes are present', () => {
    fc.assert(
      fc.property(tagNameArb.filter(t => !['input', 'textarea', 'select'].includes(t)), (tag) => {
        const el = createMockElement({ tagName: tag });
        const descriptor = extractElementDescriptor(el);
        expect(descriptor.text).toMatch(new RegExp(`^${tag}:nth-child\\(\\d+\\)$`));
      }),
      { numRuns: 100 }
    );
  });
});

// ─── Task 2.8.2: Property 4 — Typing Consolidation ───

describe('Property 4: Typing consolidation', () => {
  // Feature: nova-act-recorder, Property 4: Typing consolidation
  // **Validates: Requirements 3.1, 3.4**

  it('should produce exactly the final value from a sequence of intermediate values', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 0, maxLength: 100 }), { minLength: 1, maxLength: 50 }),
        (keystrokes) => {
          const result = consolidateTyping(keystrokes);
          // The consolidated value should be the last value in the sequence
          expect(result).toBe(keystrokes[keystrokes.length - 1]);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('should return empty string for empty keystroke sequence', () => {
    expect(consolidateTyping([])).toBe('');
    expect(consolidateTyping(null)).toBe('');
    expect(consolidateTyping(undefined)).toBe('');
  });

  it('should return the single value when only one keystroke exists', () => {
    fc.assert(
      fc.property(fc.string({ minLength: 1, maxLength: 100 }), (value) => {
        const result = consolidateTyping([value]);
        expect(result).toBe(value);
      }),
      { numRuns: 100 }
    );
  });

  it('should handle clear-and-retype: only the final value matters', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 50 }),
        fc.string({ minLength: 1, maxLength: 50 }),
        fc.string({ minLength: 1, maxLength: 50 }),
        (first, cleared, final) => {
          // Simulate: type first text, clear it (empty), type new text
          const keystrokes = [first, '', final];
          const result = consolidateTyping(keystrokes);
          expect(result).toBe(final);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('should produce exactly one action value regardless of keystroke count', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 100 }),
        fc.string({ minLength: 1, maxLength: 50 }),
        (count, finalValue) => {
          // Generate a sequence of intermediate values ending with finalValue
          const keystrokes = [];
          for (let i = 0; i < count - 1; i++) {
            keystrokes.push(finalValue.substring(0, Math.min(i + 1, finalValue.length)));
          }
          keystrokes.push(finalValue);

          const result = consolidateTyping(keystrokes);
          // Should always be exactly one value (the final one)
          expect(typeof result).toBe('string');
          expect(result).toBe(finalValue);
        }
      ),
      { numRuns: 100 }
    );
  });
});
