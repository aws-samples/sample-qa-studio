/**
 * VariableBadge / TemplateText — one dark blue badge per `{{name}}` segment
 * (small `VAR` label + value in original casing, truncated with a hover
 * title) and inline rendering of a resolved template. Segments are built by
 * hand; the resolver has its own tests.
 */
import { describe, it, expect, afterEach } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import createWrapper from '@cloudscape-design/components/test-utils/dom';

import { VariableBadge, TemplateText } from '../VariableBadge';
import type { TemplateSegment, VariableKind } from '../variableTokens';

afterEach(() => cleanup());

type VariableSegment = Extract<TemplateSegment, { type: 'variable' }>;

const variable = (overrides: Partial<VariableSegment> = {}): VariableSegment => ({
  type: 'variable',
  name: 'product',
  kind: 'regular',
  display: 'Laptop',
  placeholder: false,
  ...overrides,
});

const text = (value: string): TemplateSegment => ({ type: 'text', text: value });

function renderBadge(segment: VariableSegment) {
  const { container } = render(<VariableBadge segment={segment} />);
  const badge = createWrapper(container).findBadge();
  if (!badge) throw new Error('no Cloudscape badge rendered');
  return badge.getElement();
}

describe('VariableBadge', () => {
  it.each<VariableKind>(['regular', 'runtime', 'predefined', 'undefined'])(
    'renders kind %s as a dark blue variable badge, keeping the kind as data-kind',
    (kind) => {
      const el = renderBadge(variable({ kind }));
      expect(el).toHaveAttribute('data-testid', 'variable-badge');
      expect(el).toHaveAttribute('data-kind', kind);
      // Dark blue comes from VariableBadge.css; Cloudscape has no such badge colour.
      expect(el).toHaveClass('variable-badge');
    },
  );

  it('shows the VAR label followed by the value', () => {
    const el = renderBadge(variable());
    const label = el.querySelector('.variable-badge__label');
    const value = el.querySelector('.variable-badge__value');
    expect(label).toHaveTextContent(/^VAR$/);
    expect(value).toHaveTextContent(/^Laptop$/);
    expect(label!.compareDocumentPosition(value!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('keeps the original casing of the value', () => {
    const el = renderBadge(variable({ display: 'LapTop' }));
    expect(el.querySelector('.variable-badge__value')!.textContent).toBe('LapTop');
  });

  it('puts the full value (not the variable name) in the hover title', () => {
    const long = 'https://example.test/a/very/long/path?with=query&and=more#fragment';
    const el = renderBadge(variable({ name: 'url', display: long }));
    const value = el.querySelector('.variable-badge__value')!;
    expect(value).toHaveAttribute('title', long);
    expect(value.textContent).toBe(long);
    expect(el.querySelector('[title="url"]')).toBeNull();
  });

  it('renders placeholders in italics', () => {
    const el = renderBadge(variable({ kind: 'predefined', name: 'UniqueID', display: 'UNIQUE_ID', placeholder: true }));
    expect(el.querySelector('.variable-badge__value')).toHaveClass('variable-badge__value--placeholder');
  });

  it('does not italicise real values', () => {
    const el = renderBadge(variable());
    expect(el.querySelector('.variable-badge__value')).not.toHaveClass('variable-badge__value--placeholder');
  });

  it('renders a badge for an empty value', () => {
    const el = renderBadge(variable({ display: '' }));
    expect(el).toHaveAttribute('data-testid', 'variable-badge');
    expect(el.querySelector('.variable-badge__label')).toHaveTextContent('VAR');
    const value = el.querySelector('.variable-badge__value')!;
    expect(value.textContent).toBe('');
    expect(value).toHaveAttribute('title', '');
  });
});

describe('TemplateText', () => {
  it('renders text and badges in order, keeping the spacing around badges', () => {
    const { container } = render(
      <TemplateText segments={[text('Search for '), variable(), text(' and add it to the cart')]} />,
    );
    expect(container.textContent).toBe('Search for VARLaptop and add it to the cart');
    expect(createWrapper(container).findAllBadges()).toHaveLength(1);
  });

  it('renders adjacent badges of different kinds in order', () => {
    const { container } = render(
      <TemplateText
        segments={[
          text('user_'),
          variable({ kind: 'predefined', name: 'UniqueID', display: 'UNIQUE_ID', placeholder: true }),
          variable({ kind: 'undefined', name: 'prodcut', display: 'UNDEFINED_VALUE', placeholder: true }),
          text('!'),
        ]}
      />,
    );
    const badges = container.querySelectorAll('[data-testid="variable-badge"]');
    expect(Array.from(badges).map((b) => b.getAttribute('data-kind'))).toEqual(['predefined', 'undefined']);
    expect(container.textContent).toBe('user_VARUNIQUE_IDVARUNDEFINED_VALUE!');
  });

  it('renders plain text without badges', () => {
    const { container } = render(<TemplateText segments={[text('Open the site')]} />);
    expect(container.textContent).toBe('Open the site');
    expect(container.querySelector('[data-testid="variable-badge"]')).toBeNull();
  });

  it('renders nothing visible for no segments', () => {
    const { container } = render(<TemplateText segments={[]} />);
    expect(container.textContent).toBe('');
  });
});
