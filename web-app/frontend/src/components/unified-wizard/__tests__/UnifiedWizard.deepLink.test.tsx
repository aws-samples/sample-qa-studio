import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import UnifiedWizard from '../UnifiedWizard';

const apiGet = vi.fn();
vi.mock('../../../utils/api', () => ({
  api: { get: (...a: unknown[]) => apiGet(...a), post: vi.fn() },
  exportImportApi: { importUsecase: vi.fn() },
  devicesApi: { list: vi.fn().mockResolvedValue({ devices: [] }) },
  templateApi: { list: vi.fn().mockResolvedValue({ templates: [] }), get: vi.fn() },
}));

const SOURCE = { id: 'uc-1', name: 'Checkout', description: 'd', starting_url: 'https://shop.test', active: true };

function respond(path: string) {
  if (path === 'usecases') return Promise.resolve({ usecases: [SOURCE] });
  if (path === 'usecase/uc-1') return Promise.resolve(SOURCE);
  if (path === 'usecase/uc-1/steps') return Promise.resolve({ steps: [{ sort: 1 }, { sort: 2 }] });
  if (path === 'usecase/uc-1/variables') return Promise.resolve({ variables: [] });
  if (path === 'usecase/uc-1/headers') return Promise.resolve({ headers: {} });
  return Promise.resolve({});
}

function renderAt(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/create/new" element={<UnifiedWizard />} />
      </Routes>
    </MemoryRouter>,
  );
}

/** The Cloudscape Wizard renders the active step's title as the form header. */
async function activeStepTitle(title: string) {
  await waitFor(() => {
    expect(screen.getAllByText(title).some((el) => el.closest('h1, h2'))).toBe(true);
  });
}

describe('UnifiedWizard deep links', () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiGet.mockImplementation(respond);
  });

  it('starts at "How to start" without params', async () => {
    renderAt('/create/new');
    await activeStepTitle('How to start');
  });

  it('path=create-new opens platform selection', async () => {
    renderAt('/create/new?path=create-new&method=blank');
    await activeStepTitle('Platform selection');
  });

  it('path=import opens the upload step', async () => {
    renderAt('/create/new?path=import');
    await activeStepTitle('Upload file');
  });

  it('path=clone&sourceId=x opens select source with the source detail loaded', async () => {
    renderAt('/create/new?path=clone&sourceId=uc-1');
    await activeStepTitle('Select source');
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('usecase/uc-1/steps'));
    expect(await screen.findByText('2 step(s)')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Checkout (Copy)')).toBeInTheDocument();
  });

  it('ignores an invalid deep link', async () => {
    renderAt('/create/new?path=import&method=blank');
    await activeStepTitle('How to start');
  });

  it('does not re-apply the deep link after navigating inside the wizard', async () => {
    renderAt('/create/new?path=import');
    await activeStepTitle('Upload file');
    await userEvent.click(screen.getByRole('button', { name: 'Previous' }));
    await activeStepTitle('How to start');
  });
});
