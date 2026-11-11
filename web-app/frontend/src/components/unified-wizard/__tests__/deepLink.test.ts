import { describe, it, expect } from 'vitest';
import { deepLinkActions } from '../deepLink';
import { wizardReducer, initialWizardState } from '../wizardReducer';

const actions = (query: string) => deepLinkActions(new URLSearchParams(query));
const apply = (query: string) => actions(query).reduce(wizardReducer, initialWizardState);

describe('unified wizard deep links', () => {
  it('does nothing without a path', () => {
    expect(actions('')).toEqual([]);
    expect(actions('applicationId=app-1')).toEqual([]);
  });

  it.each(['create-new', 'clone', 'import'] as const)('path=%s selects the path and opens the next step', (path) => {
    const state = apply(`path=${path}`);
    expect(state.creationPath).toBe(path);
    expect(state.activeStepIndex).toBe(1);
  });

  it.each(['blank', 'interactive-wizard', 'template', 'user-journey'] as const)(
    'path=create-new&method=%s preselects the method (platform and basic info still come first)',
    (method) => {
      const state = apply(`path=create-new&method=${method}`);
      expect(state.creationPath).toBe('create-new');
      expect(state.creationMethod).toBe(method);
      expect(state.activeStepIndex).toBe(1);
    },
  );

  it('path=clone&sourceId=x preselects the clone source', () => {
    const state = apply('path=clone&sourceId=uc-123');
    expect(state.creationPath).toBe('clone');
    expect(state.cloneConfig.selectedUsecaseId).toBe('uc-123');
    expect(state.activeStepIndex).toBe(1);
  });

  it.each([
    'path=bogus',
    'path=CLONE',
    'path=create-new&method=bogus',
    'path=import&method=blank',
    'path=clone&method=template',
    'path=create-new&sourceId=uc-1',
    'path=import&sourceId=uc-1',
    'path=clone&sourceId=',
    'path=clone&sourceId=../../etc',
    `path=clone&sourceId=${'a'.repeat(129)}`,
  ])('ignores invalid or contradictory links: %s', (query) => {
    expect(actions(query)).toEqual([]);
    expect(apply(query)).toEqual(initialWizardState);
  });

  it('never passes raw values through', () => {
    const payloads = actions('path=create-new&method=template').map((a) => ('payload' in a ? a.payload : undefined));
    expect(payloads).toEqual(['create-new', 'template', 1]);
  });
});
