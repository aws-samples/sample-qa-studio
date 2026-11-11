/**
 * StepTypeBadge — the one step type badge shared by the step cards and the
 * Execution Steps table.
 */
import { describe, it, expect, afterEach } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import createWrapper from '@cloudscape-design/components/test-utils/dom';

import StepTypeBadge from '../StepTypeBadge';

afterEach(() => cleanup());

function badgeOf(stepType: string | undefined) {
  const { container } = render(<StepTypeBadge stepType={stepType} />);
  const badge = createWrapper(container).findBadge();
  if (!badge) throw new Error('no Cloudscape badge rendered');
  return badge.getElement();
}

describe('StepTypeBadge', () => {
  it.each([
    ['secret', 'Secret', 'red'],
    ['validation', 'Validation', 'green'],
    ['assertion', 'Assertion', 'green'],
    ['retrieve_value', 'Value', 'blue'],
    ['url', 'Goto (deprecated)', 'severity-medium'],
    ['browser', 'Browser', 'severity-medium'],
    ['transform', 'Transform', 'blue'],
    ['network_assertion', 'Network', 'blue'],
    ['repeat', 'Repeat', 'severity-low'],
    ['navigation', 'Navigation', 'grey'],
  ])('renders %s as "%s" in %s', (stepType, label, color) => {
    const el = badgeOf(stepType);
    expect(el.textContent).toBe(label);
    expect(el.className).toMatch(new RegExp(`badge-color-${color}(_|\\b)`));
  });

  it('renders download steps with the purple badge class', () => {
    const el = badgeOf('download');
    expect(el.textContent).toBe('Download');
    expect(el).toHaveClass('badge-purple');
  });

  it('falls back to Navigation for a missing or unknown step type', () => {
    expect(badgeOf(undefined).textContent).toBe('Navigation');
    expect(badgeOf('legacy_kind').textContent).toBe('Navigation');
  });
});
