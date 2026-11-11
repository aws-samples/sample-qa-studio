import { describe, it, expect } from 'vitest';
import {
  APPLICATION_CONFIG_PAGES,
  applicationConfigHref,
  applicationNavGroup,
  matchApplicationRoute,
} from '../applicationNav';

describe('matchApplicationRoute', () => {
  it('returns the application id for /applications/:id and its sub-routes', () => {
    expect(matchApplicationRoute('/applications/app-1')).toBe('app-1');
    expect(matchApplicationRoute('/applications/app-1/variables')).toBe('app-1');
    expect(matchApplicationRoute('/applications/app-1/edit')).toBe('app-1');
    expect(matchApplicationRoute('/applications/app-1/datasets/ds-9')).toBe('app-1');
  });

  it('returns null for the list page and unrelated routes', () => {
    expect(matchApplicationRoute('/applications')).toBeNull();
    expect(matchApplicationRoute('/applications/')).toBeNull();
    expect(matchApplicationRoute('/')).toBeNull();
    expect(matchApplicationRoute('/usecase/u-1')).toBeNull();
    expect(matchApplicationRoute('/test-suites/app-1/variables')).toBeNull();
  });
});

describe('applicationNavGroup', () => {
  it('is an expandable link group pointing at the applications list', () => {
    const group = applicationNavGroup('/');
    expect(group.type).toBe('expandable-link-group');
    expect(group.text).toBe('Applications');
    expect(group.href).toBe('/applications');
    expect(group.defaultExpanded).toBe(true);
  });

  it('has no children outside an application route', () => {
    expect(applicationNavGroup('/').items).toEqual([]);
    expect(applicationNavGroup('/applications').items).toEqual([]);
    expect(applicationNavGroup('/usecase/u-1').items).toEqual([]);
  });

  it('lists Variables, Secrets and Datasets for the current application', () => {
    const group = applicationNavGroup('/applications/app-1/secrets');
    expect(group.items).toEqual([
      { type: 'link', text: 'Variables', href: '/applications/app-1/variables' },
      { type: 'link', text: 'Secrets', href: '/applications/app-1/secrets' },
      { type: 'link', text: 'Datasets', href: '/applications/app-1/datasets' },
    ]);
  });

  it('keeps the children on the application detail page itself', () => {
    expect(applicationNavGroup('/applications/app-1').items).toHaveLength(3);
  });
});

describe('APPLICATION_CONFIG_PAGES / applicationConfigHref', () => {
  it('builds the href from the slug', () => {
    expect(APPLICATION_CONFIG_PAGES.map((p) => p.slug)).toEqual(['variables', 'secrets', 'datasets']);
    expect(applicationConfigHref('app-1', 'datasets')).toBe('/applications/app-1/datasets');
  });
});
