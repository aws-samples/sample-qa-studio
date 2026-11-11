/**
 * Smoke tests for the three AddItemsPicker pages: right endpoints, already-added
 * rows disabled, the right submit call and success text.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const apiGet = vi.fn();
const apiPost = vi.fn();
const apiPut = vi.fn();
const suiteGet = vi.fn();
const suiteListUsecases = vi.fn();
const suiteAddUsecases = vi.fn();
vi.mock('../../utils/api', () => ({
  api: {
    get: (...a: unknown[]) => apiGet(...a),
    post: (...a: unknown[]) => apiPost(...a),
    put: (...a: unknown[]) => apiPut(...a),
  },
  testSuites: {
    get: (...a: unknown[]) => suiteGet(...a),
    listUsecases: (...a: unknown[]) => suiteListUsecases(...a),
    addUsecases: (...a: unknown[]) => suiteAddUsecases(...a),
  },
}));

const permissions = { isAdmin: false, teams: [{ team_id: 'team-1', role: 'editor' }] };
vi.mock('../../auth', () => ({ usePermissions: () => permissions }));

import AddUsecasesToSuite from '../AddUsecasesToSuite';
import AddUsecasesToApplication from '../AddUsecasesToApplication';
import AddTestSuitesToApplication from '../AddTestSuitesToApplication';

function renderAt(path: string, pattern: string, element: React.ReactElement) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={pattern} element={element} />
      </Routes>
    </MemoryRouter>,
  );
}

const checkboxOf = (name: string) =>
  within(screen.getByText(name).closest('tr') as HTMLElement).getByRole('checkbox');

beforeEach(() => {
  vi.clearAllMocks();
  permissions.isAdmin = false;
});
afterEach(() => {
  cleanup();
});

describe('AddUsecasesToSuite', () => {
  it('disables use cases already in the suite and adds the selection', async () => {
    suiteGet.mockResolvedValue({ id: 's1', name: 'Smoke' });
    apiGet.mockResolvedValue({ usecases: [{ id: 'u1', name: 'Login' }, { id: 'u2', name: 'Checkout' }] });
    suiteListUsecases.mockResolvedValue({ usecases: [{ usecase_id: 'u1', usecase_name: 'Login' }] });
    suiteAddUsecases.mockResolvedValue({ added: 1 });

    renderAt('/test-suites/s1/add-usecases', '/test-suites/:id/add-usecases', <AddUsecasesToSuite />);

    expect(await screen.findByText('Select use cases to add to "Smoke"')).toBeInTheDocument();
    expect(apiGet).toHaveBeenCalledWith('usecases');
    expect(suiteListUsecases).toHaveBeenCalledWith('s1');
    expect(checkboxOf('Login')).toBeDisabled();
    expect(screen.getByText('Already in suite')).toBeInTheDocument();

    fireEvent.click(checkboxOf('Checkout'));
    fireEvent.click(screen.getByRole('button', { name: /Add Selected/ }));

    expect(await screen.findByText('Successfully added 1 use case(s) to the suite')).toBeInTheDocument();
    expect(suiteAddUsecases).toHaveBeenCalledWith('s1', { usecase_ids: ['u2'] });
  });
});

describe('AddUsecasesToApplication', () => {
  it('lists only use cases of the user\'s teams and posts the selection', async () => {
    apiGet.mockImplementation(async (path: string) => {
      if (path === 'applications/a1') return { id: 'a1', name: 'Shop' };
      if (path === 'usecases') {
        return {
          usecases: [
            { id: 'u1', name: 'Login', owner_team_id: 'team-1', application_id: 'a1' },
            { id: 'u2', name: 'Checkout', owner_team_id: 'team-1' },
            { id: 'u3', name: 'Other team', owner_team_id: 'team-2' },
          ],
        };
      }
      throw new Error(`unexpected GET ${path}`);
    });
    apiPost.mockResolvedValue({});

    renderAt('/applications/a1/add-usecases', '/applications/:id/add-usecases', <AddUsecasesToApplication />);

    expect(await screen.findByText('Select use cases to add to "Shop"')).toBeInTheDocument();
    expect(screen.queryByText('Other team')).not.toBeInTheDocument();
    expect(checkboxOf('Login')).toBeDisabled();
    expect(screen.getByText('Already in application')).toBeInTheDocument();

    fireEvent.click(checkboxOf('Checkout'));
    fireEvent.click(screen.getByRole('button', { name: /Add Selected/ }));

    expect(await screen.findByText('Successfully added 1 use case(s) to the application')).toBeInTheDocument();
    expect(apiPost).toHaveBeenCalledWith('applications/a1/usecases', { usecase_ids: ['u2'] });
  });

  it('shows every use case to admins', async () => {
    permissions.isAdmin = true;
    apiGet.mockImplementation(async (path: string) =>
      path === 'usecases' ? { usecases: [{ id: 'u3', name: 'Other team', owner_team_id: 'team-2' }] } : { name: 'Shop' },
    );
    renderAt('/applications/a1/add-usecases', '/applications/:id/add-usecases', <AddUsecasesToApplication />);
    expect(await screen.findByText('Other team')).toBeInTheDocument();
  });
});

describe('AddTestSuitesToApplication', () => {
  it('disables suites already in the application and PUTs each selected suite', async () => {
    apiGet.mockImplementation(async (path: string) => {
      if (path === 'applications/a1') return { id: 'a1', name: 'Shop' };
      if (path === 'test-suites') {
        return {
          suites: [
            { id: 's1', name: 'Smoke', application_id: 'a1', total_usecases: 3 },
            { id: 's2', name: 'Regression' },
            { id: 's3', name: 'Nightly' },
          ],
        };
      }
      throw new Error(`unexpected GET ${path}`);
    });
    apiPut.mockResolvedValue({});

    renderAt('/applications/a1/add-test-suites', '/applications/:id/add-test-suites', <AddTestSuitesToApplication />);

    expect(await screen.findByText('Select test suites to associate with "Shop"')).toBeInTheDocument();
    expect(checkboxOf('Smoke')).toBeDisabled();
    expect(screen.getByText('3')).toBeInTheDocument();

    fireEvent.click(checkboxOf('Regression'));
    fireEvent.click(checkboxOf('Nightly'));
    fireEvent.click(screen.getByRole('button', { name: /Add Selected/ }));

    expect(
      await screen.findByText('Successfully associated 2 test suite(s) with the application'),
    ).toBeInTheDocument();
    expect(apiPut).toHaveBeenCalledWith('test-suites/s2', { application_id: 'a1' });
    expect(apiPut).toHaveBeenCalledWith('test-suites/s3', { application_id: 'a1' });
  });
});
