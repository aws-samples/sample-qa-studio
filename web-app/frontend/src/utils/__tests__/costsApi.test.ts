import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

vi.mock('aws-amplify/auth', () => ({
  fetchAuthSession: vi.fn(async () => ({ tokens: { idToken: { toString: () => 'id-token' } } })),
}));

import {
  costsApi,
  ApiHttpError,
  ApplicationCostsResponse,
  ApplicationUsecaseCost,
  CostSummary,
  DashboardApplicationCost,
  DashboardCostsResponse,
  LedgerRow,
  UsecaseCostsResponse,
} from '../api';

const fetchMock = vi.fn();

function lastRequest() {
  const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
  return { url: String(url), method: init.method };
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

const summary: CostSummary = {
  as_of: '2026-11-04',
  window_1d: 1.42, window_1d_trend: 'up', window_1d_change_pct: 29.1, window_1d_list: 1.5,
  window_7d: 9.8, window_7d_trend: 'up', window_7d_change_pct: 10.1, window_7d_list: 10.2,
  window_30d: 42.1, window_30d_trend: null, window_30d_change_pct: null, window_30d_list: 44.0,
  by_source_30d: { nova_act: 39.0, compute: 3.1 },
  days_available: 31,
  estimated_days: 1,
  updated_at: '2026-11-05T06:02:11Z',
};

const day: LedgerRow = {
  date: '2026-11-04',
  estimated: true,
  cost: [{ service: 'nova_act', cost: 1.42, list_cost: 1.5, usage_seconds: 1076 }],
  collected_at: '2026-11-05T06:02:11Z',
};

describe('costsApi', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('application() GETs /applications/{id}/costs and returns the body unchanged (snake_case)', async () => {
    const usecaseRow: ApplicationUsecaseCost = { usecase_id: 'uc-1', name: 'Login', summary };
    const body: ApplicationCostsResponse = { summary, days: [day], usecases: [usecaseRow] };
    fetchMock.mockResolvedValue(jsonResponse(body));

    const result = await costsApi.application('app-1');

    const req = lastRequest();
    expect(req.url).toMatch(/applications\/app-1\/costs$/);
    expect(req.method).toBe('GET');
    expect(result).toEqual(body);
    expect(result.summary?.window_30d_trend).toBeNull();
    expect(result.usecases[0].summary?.by_source_30d.compute).toBe(3.1);
  });

  it('usecase() GETs /usecase/{id}/costs', async () => {
    const body: UsecaseCostsResponse = { summary: null, days: [] };
    fetchMock.mockResolvedValue(jsonResponse(body));

    const result = await costsApi.usecase('uc-1');

    const req = lastRequest();
    expect(req.url).toMatch(/usecase\/uc-1\/costs$/);
    expect(req.method).toBe('GET');
    expect(result).toEqual(body);
  });

  it('dashboard() GETs /dashboard/costs', async () => {
    const applications: DashboardApplicationCost[] = [
      { application_id: 'app-1', summary },
      { application_id: 'app-2', summary: null },
    ];
    const body: DashboardCostsResponse = { overall: summary, applications };
    fetchMock.mockResolvedValue(jsonResponse(body));

    const result = await costsApi.dashboard();

    const req = lastRequest();
    expect(req.url).toMatch(/dashboard\/costs$/);
    expect(req.method).toBe('GET');
    expect(result).toEqual(body);
  });

  it('encodes ids in the path', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ summary: null, days: [] }));
    await costsApi.usecase('a/b');
    expect(lastRequest().url).toMatch(/usecase\/a%2Fb\/costs$/);
  });

  it('rejects with an ApiHttpError that keeps the HTTP status (403 lets pages hide the card)', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ error: 'Forbidden' }, 403));

    await expect(costsApi.application('app-1')).rejects.toMatchObject<Partial<ApiHttpError>>({
      status: 403,
      body: { error: 'Forbidden' },
    });
  });
});
