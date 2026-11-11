import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { legacyCreateRoutes, unifiedWizardUrl } from '../legacyRedirects';

function Location() {
  const { pathname, search } = useLocation();
  return <div data-testid="location">{pathname + search}</div>;
}

function landOn(url: string) {
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/create/new" element={<Location />} />
        {legacyCreateRoutes()}
      </Routes>
    </MemoryRouter>,
  );
  return screen.getByTestId('location').textContent;
}

describe('legacy creation URLs redirect into the unified wizard', () => {
  it.each([
    ['/create', '/create/new'],
    ['/create/blank', '/create/new?path=create-new&method=blank'],
    ['/create/import', '/create/new?path=import'],
    ['/create/template', '/create/new?path=create-new&method=template'],
    ['/create/clone?sourceId=x', '/create/new?path=clone&sourceId=x'],
    ['/create/journey', '/create/new?path=create-new&method=user-journey'],
    ['/create/wizard/setup', '/create/new?path=create-new&method=interactive-wizard'],
    ['/wizard/session-123', '/create/new'],
  ])('%s → %s', (from, to) => {
    expect(landOn(from)).toBe(to);
  });

  it('keeps other query params (e.g. applicationId)', () => {
    expect(landOn('/create/blank?applicationId=app-1')).toBe(
      '/create/new?path=create-new&method=blank&applicationId=app-1',
    );
  });

  it('mapped params win over a conflicting old query', () => {
    expect(unifiedWizardUrl({ path: 'import' }, '?path=clone&x=1')).toBe('/create/new?path=import&x=1');
  });
});
