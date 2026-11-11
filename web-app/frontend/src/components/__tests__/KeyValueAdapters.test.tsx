/**
 * HeadersManager / SecretsManager adapters: which endpoint and body each
 * KeyValueManager operation maps to, plus one render smoke test each.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

const apiGet = vi.fn();
const apiPost = vi.fn();
const apiDelete = vi.fn();
vi.mock('../../utils/api', () => ({
  api: {
    get: (...a: unknown[]) => apiGet(...a),
    post: (...a: unknown[]) => apiPost(...a),
    delete: (...a: unknown[]) => apiDelete(...a),
  },
}));

import HeadersManager, { headersApi } from '../HeadersManager';
import SecretsManager, { secretsApi, secretStepOption } from '../SecretsManager';

beforeEach(() => {
  vi.clearAllMocks();
  apiPost.mockResolvedValue({});
  apiDelete.mockResolvedValue({});
});
afterEach(() => {
  cleanup();
});

describe('headersApi', () => {
  it('lists the header map as entries', async () => {
    apiGet.mockResolvedValue({ headers: { 'X-Env': 'staging', Authorization: 'Bearer t' } });
    expect(await headersApi('uc1').list()).toEqual([
      { key: 'X-Env', value: 'staging' },
      { key: 'Authorization', value: 'Bearer t' },
    ]);
    expect(apiGet).toHaveBeenCalledWith('usecase/uc1/headers');
  });

  it('lists nothing when the use case has no headers', async () => {
    apiGet.mockResolvedValue({});
    expect(await headersApi('uc1').list()).toEqual([]);
  });

  it('save keeps the existing headers and adds the trimmed new ones', async () => {
    await headersApi('uc1').save(
      [{ key: ' X-New ', value: ' 1 ' }, { key: 'X-Env', value: 'prod' }],
      [{ key: 'X-Env', value: 'staging' }, { key: 'X-Keep', value: 'yes' }],
    );
    expect(apiPost).toHaveBeenCalledWith('usecase/uc1/headers', {
      headers: { 'X-Env': 'prod', 'X-Keep': 'yes', 'X-New': '1' },
    });
  });

  it('remove posts the map without the key', async () => {
    await headersApi('uc1').remove('X-Env', [{ key: 'X-Env', value: 'staging' }, { key: 'X-Keep', value: 'yes' }]);
    expect(apiPost).toHaveBeenCalledWith('usecase/uc1/headers', { headers: { 'X-Keep': 'yes' } });
  });
});

describe('secretsApi', () => {
  it('lists keys and source only, even if the response carried more', async () => {
    apiGet.mockResolvedValue({
      secrets: [
        { key: 'password', secret_name: 'qa/usecase/uc1/password', description: 'd', created_at: 't', source: 'usecase' },
        { key: 'admin_password', secret_name: 'qa/application/app1/admin_password', created_at: 't', source: 'application' },
      ],
    });
    expect(await secretsApi('usecase/uc1/secrets').list()).toEqual([
      { key: 'password', source: 'usecase' },
      { key: 'admin_password', source: 'application' },
    ]);
    expect(apiGet).toHaveBeenCalledWith('usecase/uc1/secrets');
  });

  it('lists application secrets (no source) as plain keys', async () => {
    apiGet.mockResolvedValue({ secrets: [{ key: 'admin_password', secret_name: 'n', created_at: 't' }] });
    expect(await secretsApi('applications/app1/secrets').list()).toEqual([{ key: 'admin_password' }]);
    expect(apiGet).toHaveBeenCalledWith('applications/app1/secrets');
  });

  it('save posts the new secrets to the given path', async () => {
    await secretsApi('usecase/uc1/secrets').save([{ key: 'password', value: 's3cret' }], [{ key: 'other' }]);
    expect(apiPost).toHaveBeenCalledWith('usecase/uc1/secrets', { secrets: [{ key: 'password', value: 's3cret' }] });
    await secretsApi('applications/app1/secrets').save([{ key: 'k', value: 'v' }], []);
    expect(apiPost).toHaveBeenCalledWith('applications/app1/secrets', { secrets: [{ key: 'k', value: 'v' }] });
  });

  it('remove deletes by secret_key on the given path', async () => {
    await secretsApi('usecase/uc1/secrets').remove('password', []);
    expect(apiDelete).toHaveBeenCalledWith('usecase/uc1/secrets', { secret_key: 'password' });
    await secretsApi('applications/app1/secrets').remove('admin_password', []);
    expect(apiDelete).toHaveBeenCalledWith('applications/app1/secrets', { secret_key: 'admin_password' });
  });
});

describe('secretStepOption', () => {
  it('labels inherited secrets with an (application) suffix and keeps the key as value', () => {
    expect(secretStepOption({ key: 'admin_password', description: 'Admin', source: 'application' })).toEqual({
      label: 'admin_password (application)',
      value: 'admin_password',
      description: 'Admin',
    });
  });

  it('labels use-case secrets with the bare key', () => {
    expect(secretStepOption({ key: 'password', source: 'usecase' })).toEqual({
      label: 'password',
      value: 'password',
      description: undefined,
    });
    expect(secretStepOption({ key: 'legacy' }).label).toBe('legacy');
  });
});

describe('managers', () => {
  it('HeadersManager renders header names and values', async () => {
    apiGet.mockResolvedValue({ headers: { 'X-Env': 'staging' } });
    render(<HeadersManager usecaseId="uc1" />);
    expect(await screen.findByText('staging')).toBeInTheDocument();
    expect(screen.getByText('Current Headers')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save Headers' })).toBeInTheDocument();
  });

  it('HeadersManager shows the use-case empty text', async () => {
    apiGet.mockResolvedValue({ headers: {} });
    render(<HeadersManager usecaseId="uc1" />);
    expect(await screen.findByText('No headers configured for this usecase.')).toBeInTheDocument();
  });

  it('SecretsManager renders secret keys only', async () => {
    apiGet.mockResolvedValue({ secrets: [{ key: 'password', source: 'usecase' }] });
    render(<SecretsManager usecaseId="uc1" />);
    expect(await screen.findByText('password')).toBeInTheDocument();
    expect(screen.getByText('Current Secrets')).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: 'Secret Value' })).not.toBeInTheDocument();
    expect(screen.queryByText('Application')).not.toBeInTheDocument();
  });

  it('SecretsManager marks inherited application secrets read-only with an Application badge', async () => {
    apiGet.mockResolvedValue({
      secrets: [{ key: 'password', source: 'usecase' }, { key: 'admin_password', source: 'application' }],
    });
    render(<SecretsManager usecaseId="uc1" />);
    await screen.findByText('admin_password');
    expect(screen.getByText('Application').closest('tr')).toHaveTextContent('admin_password');
    const deleteButtons = screen.getAllByRole('button', { name: 'Delete' });
    expect(deleteButtons).toHaveLength(1);
    expect(deleteButtons[0].closest('tr')).toHaveTextContent('password');
  });

  it('SecretsManager shows the use-case empty text', async () => {
    apiGet.mockResolvedValue({ secrets: [] });
    render(<SecretsManager usecaseId="uc1" />);
    expect(await screen.findByText('No secrets configured for this usecase.')).toBeInTheDocument();
  });
});
