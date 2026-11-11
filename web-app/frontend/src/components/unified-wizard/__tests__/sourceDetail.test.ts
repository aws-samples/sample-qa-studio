import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiGet = vi.fn();
vi.mock('../../../utils/api', () => ({ api: { get: (...a: unknown[]) => apiGet(...a) } }));

import { fetchTemplateDetail, fetchUsecaseDetail } from '../sourceDetail';

function respond(map: Record<string, unknown | Error>) {
  apiGet.mockImplementation(async (path: string) => {
    if (!(path in map)) throw new Error(`unexpected GET ${path}`);
    const value = map[path];
    if (value instanceof Error) throw value;
    return value;
  });
}

beforeEach(() => {
  apiGet.mockReset();
});

describe('fetchUsecaseDetail', () => {
  it('combines the use case, steps, variables and headers', async () => {
    respond({
      'usecase/u1': { id: 'u1', name: 'Login' },
      'usecase/u1/steps': { steps: [{ sk: 'STEP#1' }] },
      'usecase/u1/variables': { variables: [{ name: 'user' }] },
      'usecase/u1/headers': { headers: { 'X-Env': 'dev' } },
    });
    expect(await fetchUsecaseDetail('u1')).toEqual({
      id: 'u1',
      name: 'Login',
      steps: [{ sk: 'STEP#1' }],
      variables: [{ name: 'user' }],
      headers: { 'X-Env': 'dev' },
    });
  });

  it('falls back to empty variables and headers when those requests fail', async () => {
    respond({
      'usecase/u1': { id: 'u1', name: 'Login' },
      'usecase/u1/steps': { steps: [] },
      'usecase/u1/variables': new Error('403'),
      'usecase/u1/headers': new Error('500'),
    });
    expect(await fetchUsecaseDetail('u1')).toEqual({
      id: 'u1',
      name: 'Login',
      steps: [],
      variables: [],
      headers: {},
    });
  });

  it('fails when the use case or its steps cannot be loaded', async () => {
    respond({
      'usecase/u1': { id: 'u1' },
      'usecase/u1/steps': new Error('steps down'),
      'usecase/u1/variables': { variables: [] },
      'usecase/u1/headers': { headers: {} },
    });
    await expect(fetchUsecaseDetail('u1')).rejects.toThrow('steps down');
  });

  it('treats missing lists in the responses as empty', async () => {
    respond({
      'usecase/u1': { id: 'u1' },
      'usecase/u1/steps': {},
      'usecase/u1/variables': {},
      'usecase/u1/headers': {},
    });
    expect(await fetchUsecaseDetail('u1')).toEqual({ id: 'u1', steps: [], variables: [], headers: {} });
  });
});

describe('fetchTemplateDetail', () => {
  it('combines the template, steps and variables', async () => {
    respond({
      'templates/t1': { id: 't1', name: 'Checkout' },
      'templates/t1/steps': { steps: [{ sk: 'STEP#1' }] },
      'templates/t1/variables': { variables: [{ name: 'card' }] },
    });
    expect(await fetchTemplateDetail('t1')).toEqual({
      id: 't1',
      name: 'Checkout',
      steps: [{ sk: 'STEP#1' }],
      variables: [{ name: 'card' }],
    });
  });

  it('falls back to empty variables when that request fails', async () => {
    respond({
      'templates/t1': { id: 't1', name: 'Checkout' },
      'templates/t1/steps': { steps: [] },
      'templates/t1/variables': new Error('boom'),
    });
    expect((await fetchTemplateDetail('t1')).variables).toEqual([]);
  });

  it('fails when the template cannot be loaded', async () => {
    respond({
      'templates/t1': new Error('gone'),
      'templates/t1/steps': { steps: [] },
      'templates/t1/variables': { variables: [] },
    });
    await expect(fetchTemplateDetail('t1')).rejects.toThrow('gone');
  });
});
