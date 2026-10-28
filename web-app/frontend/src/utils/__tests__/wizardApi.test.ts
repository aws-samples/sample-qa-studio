import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

vi.mock('aws-amplify/auth', () => ({
  fetchAuthSession: vi.fn(async () => ({ tokens: { idToken: { toString: () => 'id-token' } } })),
}));

import { wizardApi } from '../api';

const fetchMock = vi.fn();

function lastRequest() {
  const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
  return { url: String(url), method: init.method, body: JSON.parse(init.body) };
}

describe('wizardApi session routes send the session usecaseId (H-2)', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('addStep posts the step fields plus usecaseId', async () => {
    await wizardApi.addStep('sess-1', 'uc-1', { instruction: 'Click login', step_type: 'action' });
    const req = lastRequest();
    expect(req.url).toMatch(/wizard\/sess-1\/step$/);
    expect(req.method).toBe('POST');
    expect(req.body).toEqual({ instruction: 'Click login', step_type: 'action', usecaseId: 'uc-1' });
  });

  it('addStep never lets a step field override the session usecaseId', async () => {
    await wizardApi.addStep('sess-1', 'uc-1', { usecaseId: 'uc-other', instruction: 'x' });
    expect(lastRequest().body.usecaseId).toBe('uc-1');
  });

  it('restart posts usecaseId', async () => {
    await wizardApi.restart('sess-1', 'uc-1');
    const req = lastRequest();
    expect(req.url).toMatch(/wizard\/sess-1\/restart$/);
    expect(req.body).toEqual({ usecaseId: 'uc-1' });
  });

  it('sendRecordingCommand posts usecaseId and action', async () => {
    await wizardApi.sendRecordingCommand('sess-1', 'uc-1', 'recording_stop');
    const req = lastRequest();
    expect(req.url).toMatch(/wizard\/sess-1\/command$/);
    expect(req.body).toEqual({ usecaseId: 'uc-1', action: 'recording_stop' });
  });

  it('encodes the session id in the path', async () => {
    await wizardApi.restart('a/b', 'uc-1');
    expect(lastRequest().url).toMatch(/wizard\/a%2Fb\/restart$/);
  });
});
