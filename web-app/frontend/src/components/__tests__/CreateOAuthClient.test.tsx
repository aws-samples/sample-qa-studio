import React from 'react';
import { render, waitFor, fireEvent, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import createWrapper from '@cloudscape-design/components/test-utils/dom';

const mockUsePermissions = vi.fn();
vi.mock('../../auth', () => ({ usePermissions: () => mockUsePermissions() }));

const mockGet = vi.fn();
const mockCreate = vi.fn();
const mockScopes = vi.fn();
vi.mock('../../utils/api', () => ({
  api: { get: (...args: any[]) => mockGet(...args) },
  oauthClientApi: { create: (...args: any[]) => mockCreate(...args) },
  scopesApi: { list: () => mockScopes() },
}));

import CreateOAuthClient from '../CreateOAuthClient';

const perms = (isAdmin: boolean, teams: Array<{ team_id: string; role: string }>) => ({
  isAdmin,
  isTeamLead: false,
  teams: teams.map((t) => ({ ...t, group_name: `team-${t.team_id}-${t.role}` })),
  hasScope: () => true,
  scopes: [],
  isLoading: false,
});

const scope = (value: string) => ({ value, label: value, description: '' });

async function renderForm() {
  const result = render(<MemoryRouter><CreateOAuthClient /></MemoryRouter>);
  await waitFor(() => expect(mockScopes).toHaveBeenCalled());
  return createWrapper(result.container);
}

describe('CreateOAuthClient team binding (H-2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockScopes.mockResolvedValue({
      scopes: [scope('api/admin'), scope('api/teams.manage'), scope('api/usecases.execute')],
      resource_server_identifier: 'api',
    });
    mockGet.mockImplementation(async (endpoint: string) => {
      const id = decodeURIComponent(endpoint.split('/')[1] || '');
      return { id, name: `Team ${id}` };
    });
    mockCreate.mockResolvedValue({ client_id: 'c', client_secret: 's', scopes: [] });
  });

  it('offers only teams where the user is editor or team lead', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [
      { team_id: 'a', role: 'editor' }, { team_id: 'b', role: 'viewer' }, { team_id: 'c', role: 'team_lead' },
    ]));
    await renderForm();
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));
    expect(mockGet).toHaveBeenCalledWith('teams/a');
    expect(mockGet).toHaveBeenCalledWith('teams/c');
    expect(mockGet).not.toHaveBeenCalledWith('teams/b');
  });

  it('admins get every team', async () => {
    mockUsePermissions.mockReturnValue(perms(true, []));
    mockGet.mockResolvedValue([{ id: 't1', name: 'One' }]);
    await renderForm();
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('teams'));
  });

  it('never offers api/admin or api/teams.manage', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'a', role: 'editor' }]));
    const wrapper = await renderForm();
    const multiselect = wrapper.findMultiselect()!;
    await waitFor(() => expect(multiselect.findTrigger().getElement().hasAttribute('disabled')).toBe(false));
    act(() => multiselect.openDropdown());
    const labels = multiselect.findDropdown().findOptions().map((o) => o.getElement().textContent);
    expect(labels.some((l) => l?.includes('api/usecases.execute'))).toBe(true);
    expect(labels.some((l) => l?.includes('api/admin'))).toBe(false);
    expect(labels.some((l) => l?.includes('api/teams.manage'))).toBe(false);
  });

  it('requires a team and sends teamId', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'a', role: 'editor' }]));
    const wrapper = await renderForm();
    wrapper.findInput()!.setInputValue('ci-client');
    const multiselect = wrapper.findMultiselect()!;
    await waitFor(() => expect(multiselect.findTrigger().getElement().hasAttribute('disabled')).toBe(false));
    act(() => multiselect.openDropdown());
    act(() => multiselect.selectOptionByValue('api/usecases.execute'));

    const createButton = () => wrapper.findAllButtons()
      .find((b) => b.getElement().textContent === 'Create Client')!;
    expect(createButton().getElement().hasAttribute('disabled')).toBe(true);

    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('teams/a'));
    const select = wrapper.findSelect()!;
    act(() => select.openDropdown());
    await waitFor(() => expect(select.findDropdown().findOptions().length).toBe(1));
    act(() => select.selectOptionByValue('a'));

    expect(createButton().getElement().hasAttribute('disabled')).toBe(false);
    fireEvent.click(createButton().getElement());
    await waitFor(() => expect(mockCreate).toHaveBeenCalled());
    expect(mockCreate.mock.calls[0][0]).toEqual({ name: 'ci-client', scopes: ['api/usecases.execute'], teamId: 'a' });
  });
});
