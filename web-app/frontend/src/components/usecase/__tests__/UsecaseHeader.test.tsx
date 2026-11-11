import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import UsecaseHeader from '../UsecaseHeader';
import { ELECTRON_CI_RUNNER_ONLY_MESSAGE } from '../../common/platform';

const apiGet = vi.fn();
const apiPost = vi.fn();
const navigate = vi.fn();

vi.mock('react-router-dom', () => ({
  useNavigate: () => navigate,
}));
vi.mock('../../../utils/api', () => ({
  api: { get: (...a: unknown[]) => apiGet(...a), post: (...a: unknown[]) => apiPost(...a) },
  exportImportApi: { exportUsecase: vi.fn() },
}));
vi.mock('../SubscriptionButton', () => ({ default: () => <div data-testid="subscription" /> }));
vi.mock('../../common/Breadcrumb', () => ({ default: () => <nav /> }));

function usecase(platform: string) {
  return { id: 'u-1', name: 'Harness smoke', test_platform: platform };
}

describe('UsecaseHeader execution controls per platform', () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
    apiPost.mockResolvedValue({});
    navigate.mockReset();
  });

  it('lets a web usecase trigger a cloud execution', async () => {
    apiGet.mockResolvedValue(usecase('web'));
    render(<UsecaseHeader usecaseId="u-1" />);
    const button = await screen.findByRole('button', { name: /trigger execution/i });
    expect(button).toBeEnabled();
    expect(button).not.toHaveAttribute('aria-disabled');
    await userEvent.click(button);
    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith('usecase/u-1/execute?trigger-type=OnDemandHeadless', {}),
    );
  });

  it('disables cloud execution for an electron usecase and explains why', async () => {
    apiGet.mockResolvedValue(usecase('electron'));
    render(<UsecaseHeader usecaseId="u-1" />);
    const button = await screen.findByRole('button', { name: /trigger execution/i });
    // Cloudscape keeps a button with a disabledReason focusable (aria-disabled)
    // so the explanation tooltip can be reached by keyboard.
    expect(button).toHaveAttribute('aria-disabled', 'true');
    await userEvent.click(button);
    expect(apiPost).not.toHaveBeenCalled();
    await userEvent.hover(button);
    // Rendered twice by Cloudscape: the aria-describedby text and the visible tooltip.
    const explanations = await screen.findAllByText(ELECTRON_CI_RUNNER_ONLY_MESSAGE);
    expect(explanations.length).toBeGreaterThanOrEqual(1);
    expect(button).toHaveAccessibleDescription(ELECTRON_CI_RUNNER_ONLY_MESSAGE);
  });

  it('offers no use-case-level OnDemand item in the execute dropdown', async () => {
    apiGet.mockResolvedValue(usecase('web'));
    render(<UsecaseHeader usecaseId="u-1" />);
    await screen.findByRole('button', { name: /trigger execution/i });
    const toggle = screen
      .getAllByRole('button')
      .find((b) => b.getAttribute('aria-haspopup') !== null);
    expect(toggle).toBeDefined();
    await userEvent.click(toggle!);
    expect(await screen.findByText('Clone Use Case')).toBeInTheDocument();
    expect(screen.queryByText(/OnDemand \(Local\)/)).not.toBeInTheDocument();
  });

  it('"Clone Use Case" opens the unified wizard with the source preselected', async () => {
    apiGet.mockResolvedValue(usecase('web'));
    render(<UsecaseHeader usecaseId="u-1" />);
    await screen.findByRole('button', { name: /trigger execution/i });
    const toggle = screen
      .getAllByRole('button')
      .find((b) => b.getAttribute('aria-haspopup') !== null);
    await userEvent.click(toggle!);
    await userEvent.click(await screen.findByText('Clone Use Case'));
    expect(navigate).toHaveBeenCalledWith('/create/new?path=clone&sourceId=u-1');
  });

  it('shows the platform badge next to the title', async () => {
    apiGet.mockResolvedValue(usecase('electron'));
    render(<UsecaseHeader usecaseId="u-1" />);
    expect(await screen.findByText('Electron')).toBeInTheDocument();
  });
});
