/**
 * UsecaseVariables is a thin adapter: `variablesApi('usecase/{id}/variables')`
 * mapped onto the shared VariablesEditor. Checks the endpoint/body mapping and
 * that inherited application rows render read-only and are never posted.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

const apiGet = vi.fn();
const apiPost = vi.fn();
vi.mock('../../../utils/api', () => ({
  api: {
    get: (...a: unknown[]) => apiGet(...a),
    post: (...a: unknown[]) => apiPost(...a),
  },
}));

import UsecaseVariables from '../UsecaseVariables';
import { variablesApi } from '../../common/VariablesEditor';

beforeEach(() => {
  apiGet.mockReset();
  apiPost.mockReset();
  apiPost.mockResolvedValue({});
});
afterEach(() => {
  cleanup();
});

describe('variablesApi', () => {
  it('lists rows with their source and normalises missing fields', async () => {
    apiGet.mockResolvedValue({
      variables: [
        { key: 'base_api', value: 'https://a', source: 'application' },
        { key: 'user', value: 'alice', source: 'usecase' },
        { key: 'plain', value: 'p' },
        { key: 'weird', value: 'w', source: 'cli' },
        { value: 'no-key' },
      ],
    });
    expect(await variablesApi('usecase/uc1/variables').list()).toEqual([
      { key: 'base_api', value: 'https://a', source: 'application' },
      { key: 'user', value: 'alice', source: 'usecase' },
      { key: 'plain', value: 'p' },
      { key: 'weird', value: 'w' },
      { key: '', value: 'no-key' },
    ]);
    expect(apiGet).toHaveBeenCalledWith('usecase/uc1/variables');
  });

  it('lists nothing when the response carries no variables', async () => {
    apiGet.mockResolvedValue({});
    expect(await variablesApi('usecase/uc1/variables').list()).toEqual([]);
  });

  it('save posts key/value only, dropping source', async () => {
    await variablesApi('usecase/uc1/variables').save([
      { key: 'user', value: 'bob', source: 'usecase' },
      { key: 'env', value: 'staging' },
    ]);
    expect(apiPost).toHaveBeenCalledWith('usecase/uc1/variables', {
      variables: [{ key: 'user', value: 'bob' }, { key: 'env', value: 'staging' }],
    });
  });
});

describe('UsecaseVariables', () => {
  it('loads the effective list, shows inherited rows read-only and posts only its own rows', async () => {
    apiGet.mockResolvedValue({
      variables: [
        { key: 'base_api', value: 'https://a', source: 'application' },
        { key: 'user', value: 'alice', source: 'usecase' },
      ],
    });
    render(<UsecaseVariables usecaseId="uc1" />);

    expect(await screen.findByText('base_api')).toBeInTheDocument();
    expect(apiGet).toHaveBeenCalledWith('usecase/uc1/variables');
    expect(screen.getByText('Application')).toBeInTheDocument();
    expect(screen.queryByDisplayValue('base_api')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Key 1')).toHaveValue('user');

    fireEvent.change(screen.getByLabelText('Value 1'), { target: { value: 'bob' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith('usecase/uc1/variables', { variables: [{ key: 'user', value: 'bob' }] }),
    );
    expect(JSON.stringify(apiPost.mock.calls)).not.toContain('base_api');
  });

  it('remounts for another use case', async () => {
    apiGet.mockResolvedValue({ variables: [] });
    const { rerender } = render(<UsecaseVariables usecaseId="uc1" />);
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('usecase/uc1/variables'));
    rerender(<UsecaseVariables usecaseId="uc2" />);
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('usecase/uc2/variables'));
  });
});
