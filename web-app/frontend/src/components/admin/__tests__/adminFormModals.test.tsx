/**
 * The four admin modals on FormModal: labels, validation messages, the
 * submitted values, API error text and reset on Cancel.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import createWrapper from '@cloudscape-design/components/test-utils/dom';

import CreateTeamModal from '../CreateTeamModal';
import AddMemberModal from '../AddMemberModal';
import CreateUserModal from '../CreateUserModal';
import GrantAccessModal from '../GrantAccessModal';

afterEach(() => {
  cleanup();
});

/** Cloudscape Input renders the testid on a wrapper; the <input> is inside. */
function typeInto(testId: string, value: string) {
  const el = screen.getByTestId(testId);
  const input = el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' ? el : (el.querySelector('input, textarea') as HTMLElement);
  fireEvent.change(input, { target: { value } });
}

/** Open a Cloudscape Select (the modal renders in a portal) and pick an option by value. */
function choose(testId: string, value: string) {
  const select = createWrapper(document.body).findSelect(`[data-testid="${testId}"]`)!;
  act(() => select.openDropdown());
  act(() => select.selectOptionByValue(value));
}

describe('CreateTeamModal', () => {
  const renderModal = (onSubmit = vi.fn().mockResolvedValue(undefined), onDismiss = vi.fn()) => {
    render(<CreateTeamModal visible onDismiss={onDismiss} onSubmit={onSubmit} />);
    return { onSubmit, onDismiss };
  };

  it('renders its labels', () => {
    renderModal();
    expect(screen.getByText('Create Team')).toBeInTheDocument();
    expect(screen.getByText('Team name')).toBeInTheDocument();
    expect(screen.getByText('Description')).toBeInTheDocument();
    expect(screen.getByTestId('create-team-submit')).toHaveTextContent('Create');
  });

  it('requires a name', async () => {
    const { onSubmit } = renderModal();
    fireEvent.click(screen.getByTestId('create-team-submit'));
    expect(await screen.findByText('Team name is required')).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('submits the trimmed values and closes', async () => {
    const { onSubmit, onDismiss } = renderModal();
    typeInto('create-team-name-input', '  QA  ');
    typeInto('create-team-description-input', ' Testers ');
    fireEvent.click(screen.getByTestId('create-team-submit'));
    await waitFor(() => expect(onDismiss).toHaveBeenCalled());
    expect(onSubmit).toHaveBeenCalledWith('QA', 'Testers');
  });

  it('shows the API error, or the fallback', async () => {
    renderModal(vi.fn().mockRejectedValueOnce(new Error('Team exists')).mockRejectedValueOnce({}));
    typeInto('create-team-name-input', 'QA');
    fireEvent.click(screen.getByTestId('create-team-submit'));
    expect(await screen.findByText('Team exists')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('create-team-submit'));
    expect(await screen.findByText('Failed to create team')).toBeInTheDocument();
  });

  it('Cancel clears the fields', async () => {
    const { onDismiss } = renderModal();
    typeInto('create-team-name-input', 'QA');
    fireEvent.click(screen.getByTestId('create-team-cancel'));
    expect(onDismiss).toHaveBeenCalled();
    expect(screen.getByTestId('create-team-name-input').querySelector('input') ?? screen.getByTestId('create-team-name-input')).toHaveValue('');
  });
});

describe('AddMemberModal', () => {
  const renderModal = (onSubmit = vi.fn().mockResolvedValue(undefined)) => {
    const onDismiss = vi.fn();
    render(<AddMemberModal visible onDismiss={onDismiss} onSubmit={onSubmit} allowedRoles={['editor', 'viewer']} />);
    return { onSubmit, onDismiss };
  };

  it('validates the user and the role, in that order', async () => {
    const { onSubmit } = renderModal();
    expect(screen.getByText('Add Team Member')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('add-member-submit'));
    expect(await screen.findByText('User email or ID is required')).toBeInTheDocument();
    typeInto('add-member-user-input', 'a@example.com');
    fireEvent.click(screen.getByTestId('add-member-submit'));
    expect(await screen.findByText('Role is required')).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('submits user and role', async () => {
    const { onSubmit, onDismiss } = renderModal();
    typeInto('add-member-user-input', ' a@example.com ');
    choose('add-member-role-select', 'editor');
    fireEvent.click(screen.getByTestId('add-member-submit'));
    await waitFor(() => expect(onDismiss).toHaveBeenCalled());
    expect(onSubmit).toHaveBeenCalledWith('a@example.com', 'editor');
  });

  it('shows the fallback error', async () => {
    renderModal(vi.fn().mockRejectedValue({}));
    typeInto('add-member-user-input', 'a@example.com');
    choose('add-member-role-select', 'viewer');
    fireEvent.click(screen.getByTestId('add-member-submit'));
    expect(await screen.findByText('Failed to add member')).toBeInTheDocument();
  });
});

describe('CreateUserModal', () => {
  const TEAMS = [{ id: 't1', name: 'QA' }] as any;
  const renderModal = (onSubmit = vi.fn().mockResolvedValue(undefined)) => {
    const onDismiss = vi.fn();
    render(<CreateUserModal visible onDismiss={onDismiss} onSubmit={onSubmit} availableTeams={TEAMS} />);
    return { onSubmit, onDismiss };
  };

  it('validates the email', async () => {
    renderModal();
    expect(screen.getByText('Create User', { selector: 'h2 *, h2' })).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('create-user-submit'));
    expect(await screen.findByText('Email is required')).toBeInTheDocument();
    typeInto('create-user-email-input', 'not-an-email');
    fireEvent.click(screen.getByTestId('create-user-submit'));
    expect(await screen.findByText('Invalid email format')).toBeInTheDocument();
  });

  it('submits email, team and role', async () => {
    const { onSubmit, onDismiss } = renderModal();
    typeInto('create-user-email-input', 'a@example.com');
    choose('create-user-role-select', 'editor');
    choose('create-user-team-select', 't1');
    fireEvent.click(screen.getByTestId('create-user-submit'));
    await waitFor(() => expect(onDismiss).toHaveBeenCalled());
    expect(onSubmit).toHaveBeenCalledWith('a@example.com', 't1', 'editor');
  });

  it('hides the team for admins and never sends one', async () => {
    const { onSubmit } = renderModal();
    typeInto('create-user-email-input', 'a@example.com');
    choose('create-user-role-select', 'admin');
    expect(screen.queryByTestId('create-user-team-select')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('create-user-submit'));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith('a@example.com', undefined, 'admin'));
  });

  it('shows the fallback error', async () => {
    renderModal(vi.fn().mockRejectedValue({}));
    typeInto('create-user-email-input', 'a@example.com');
    fireEvent.click(screen.getByTestId('create-user-submit'));
    expect(await screen.findByText('Failed to create user')).toBeInTheDocument();
  });
});

describe('GrantAccessModal', () => {
  const renderModal = (onSubmit = vi.fn().mockResolvedValue(undefined)) => {
    const onDismiss = vi.fn();
    render(
      <GrantAccessModal
        visible
        onDismiss={onDismiss}
        onSubmit={onSubmit}
        availableTeams={[{ id: 't2', name: 'Payments' }] as any}
        availableApps={[{ id: 'a1', name: 'Shop' }]}
      />,
    );
    return { onSubmit, onDismiss };
  };

  it('validates team, application and level, in that order', async () => {
    renderModal();
    expect(screen.getByText('Grant Shared Access')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('grant-access-submit'));
    expect(await screen.findByText('Target team is required')).toBeInTheDocument();
    choose('grant-access-team-select', 't2');
    fireEvent.click(screen.getByTestId('grant-access-submit'));
    expect(await screen.findByText('Application is required')).toBeInTheDocument();
    choose('grant-access-app-select', 'a1');
    fireEvent.click(screen.getByTestId('grant-access-submit'));
    expect(await screen.findByText('Access level is required')).toBeInTheDocument();
  });

  it('submits team, application and level', async () => {
    const { onSubmit, onDismiss } = renderModal();
    choose('grant-access-team-select', 't2');
    choose('grant-access-app-select', 'a1');
    choose('grant-access-level-select', 'execute');
    fireEvent.click(screen.getByTestId('grant-access-submit'));
    await waitFor(() => expect(onDismiss).toHaveBeenCalled());
    expect(onSubmit).toHaveBeenCalledWith('t2', 'a1', 'execute');
  });

  it('shows the fallback error', async () => {
    renderModal(vi.fn().mockRejectedValue({}));
    choose('grant-access-team-select', 't2');
    choose('grant-access-app-select', 'a1');
    choose('grant-access-level-select', 'view');
    fireEvent.click(screen.getByTestId('grant-access-submit'));
    expect(await screen.findByText('Failed to grant access')).toBeInTheDocument();
  });
});
