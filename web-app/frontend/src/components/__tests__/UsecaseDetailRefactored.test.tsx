/**
 * UsecaseDetailRefactored: the info section and the cost card share a 9:3
 * Grid; the card loads through `costsApi.usecase`, is hidden on 403/404 and
 * shows an error Alert otherwise. Section components are stubbed; the cost
 * card is the real one.
 */
import React from 'react';
import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import createWrapper from '@cloudscape-design/components/test-utils/dom';

const apiDelete = vi.fn();
const costsUsecase = vi.fn();
vi.mock('../../utils/api', async () => {
  const actual = await vi.importActual<typeof import('../../utils/api')>('../../utils/api');
  return {
    ...actual,
    api: { ...actual.api, delete: (...a: unknown[]) => apiDelete(...a) },
    costsApi: { ...actual.costsApi, usecase: (...a: unknown[]) => costsUsecase(...a) },
  };
});

const stub = (testId: string) => ({ default: ({ usecaseId }: { usecaseId: string }) => <div data-testid={testId}>{usecaseId}</div> });
vi.mock('../usecase/UsecaseHeader', () => stub('section-header'));
vi.mock('../usecase/UsecaseInfo', () => stub('section-info'));
vi.mock('../usecase/UsecaseSchedule', () => stub('section-schedule'));
vi.mock('../usecase/UsecaseVariables', () => stub('section-variables'));
vi.mock('../SecretsManager', () => stub('section-secrets'));
vi.mock('../HeadersManager', () => stub('section-headers'));
vi.mock('../usecase/WorkflowSteps', () => stub('section-steps'));
vi.mock('../usecase/ExecutionHistory', () => stub('section-history'));
vi.mock('../usecase/UsecaseHooks', () => stub('section-hooks'));

import UsecaseDetailRefactored from '../UsecaseDetailRefactored';
import { SplitPanelProvider } from '../common/splitPanel';

const summary = {
  as_of: '2026-11-04',
  window_1d: 1.42, window_1d_trend: 'up', window_1d_change_pct: 29.1, window_1d_list: 1.5,
  window_7d: 9.8, window_7d_trend: 'down', window_7d_change_pct: -10.1, window_7d_list: 10.2,
  window_30d: 42.1, window_30d_trend: null, window_30d_change_pct: null, window_30d_list: 44.0,
  by_source_30d: { nova_act: 42.1 },
  days_available: 31,
  estimated_days: 0,
  updated_at: '2026-11-05T06:02:11Z',
};

function httpError(status: number) {
  const err = new Error(`HTTP ${status}`);
  (err as Error & { status: number }).status = status;
  return err;
}

function renderPage() {
  return render(
    <SplitPanelProvider>
      <MemoryRouter initialEntries={['/usecase/uc-1']}>
        <Routes>
          <Route path="/usecase/:id" element={<UsecaseDetailRefactored />} />
        </Routes>
      </MemoryRouter>
    </SplitPanelProvider>,
  );
}

// The page lazy-loads the cost card (Cloudscape BarChart); under full-suite
// load its first transform exceeds the 1 s `findBy` timeout. Pay it up front.
beforeAll(async () => {
  await import('../common/cost/UsecaseCostCard');
});
beforeEach(() => {
  apiDelete.mockReset();
  costsUsecase.mockReset();
});
afterEach(() => {
  cleanup();
});

describe('UsecaseDetailRefactored cost card', () => {
  it('renders the cost card next to the info section and requests costs once', async () => {
    costsUsecase.mockResolvedValue({ summary, days: [] });
    renderPage();
    expect(await screen.findByTestId('section-info')).toHaveTextContent('uc-1');
    expect(await screen.findByText('$42.10')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Cost' })).toBeInTheDocument();
    expect(screen.getByText('Source: Nova Act · Cost Explorer as of 2026-11-04')).toBeInTheDocument();
    expect(costsUsecase).toHaveBeenCalledTimes(1);
    expect(costsUsecase).toHaveBeenCalledWith('uc-1');
  });

  it('places info and cost card in a 9:3 grid', async () => {
    costsUsecase.mockResolvedValue({ summary, days: [] });
    renderPage();
    const info = await screen.findByTestId('section-info');
    await screen.findByText('$42.10');
    const heading = screen.getByRole('heading', { name: 'Cost' });
    const grid = createWrapper(document.body).findGrid()!;
    expect(grid).not.toBeNull();
    expect(grid.findColumn(1)!.getElement()).toContainElement(info);
    expect(grid.findColumn(2)!.getElement()).toContainElement(heading);
    expect(grid.findColumn(3)).toBeNull();
  });

  it('shows no cost card when the API answers 403', async () => {
    costsUsecase.mockRejectedValue(httpError(403));
    renderPage();
    await screen.findByTestId('section-info');
    await vi.waitFor(() => expect(costsUsecase).toHaveBeenCalled());
    await vi.waitFor(() => expect(screen.queryByRole('heading', { name: 'Cost' })).not.toBeInTheDocument());
    expect(screen.queryByText(/No cost data yet/)).not.toBeInTheDocument();
  });

  it('shows an error alert inside the card when the API fails', async () => {
    costsUsecase.mockRejectedValue(httpError(500));
    renderPage();
    expect(await screen.findByText('HTTP 500')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Cost' })).toBeInTheDocument();
  });

  it('keeps the existing sections and tabs', async () => {
    costsUsecase.mockResolvedValue({ summary: null, days: [] });
    renderPage();
    expect(await screen.findByTestId('section-header')).toBeInTheDocument();
    expect(await screen.findByTestId('section-history')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Workflow Steps' })).toBeInTheDocument();
  });
});
