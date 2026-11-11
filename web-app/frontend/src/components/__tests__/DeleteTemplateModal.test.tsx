/**
 * DeleteTemplateModal — shows which tests use the template(s) before deleting.
 *
 * Deleting a template keeps the steps of the tests that inserted it and only
 * removes the template link; the modal says so with the real test names
 * (GET /templates/{id}/usages).  A failing usage lookup never blocks the
 * deletion: the modal falls back to its plain text.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

import DeleteTemplateModal from '../DeleteTemplateModal';

const apiGet = vi.fn();
vi.mock('../../utils/api', () => ({
  api: { get: (...a: unknown[]) => apiGet(...a) },
}));

afterEach(() => cleanup());
// Braces matter: a hook that *returns* a vi.fn makes Vitest call it as teardown.
beforeEach(() => {
  apiGet.mockReset();
});

const LOGIN = { id: 't1', name: 'Login' };
const COOKIES = { id: 't2', name: 'Cookie banner' };

function renderModal(templates = [LOGIN]) {
  return render(
    <DeleteTemplateModal
      visible
      templateName={templates.length === 1 ? templates[0].name : `${templates.length} templates`}
      templates={templates}
      onDismiss={vi.fn()}
      onConfirm={vi.fn()}
    />,
  );
}

describe('DeleteTemplateModal — usages', () => {
  it('shows a spinner while usages load', async () => {
    apiGet.mockImplementation(() => new Promise(() => undefined));
    renderModal();
    expect(await screen.findByText(/Checking which tests use/i)).toBeInTheDocument();
    expect(apiGet).toHaveBeenCalledWith('templates/t1/usages');
  });

  it('says the template is not used when there are no usages', async () => {
    apiGet.mockResolvedValue({ usages: [], count: 0 });
    renderModal();
    expect(await screen.findByText('"Login" is not used by any test.')).toBeInTheDocument();
    expect(screen.queryByText(/Steps in those tests are kept/)).not.toBeInTheDocument();
  });

  it('lists the tests using the template and the keep-steps note', async () => {
    apiGet.mockResolvedValue({
      usages: [{ usecase_id: 'uc-1', name: 'Checkout' }, { usecase_id: 'uc-2', name: 'Refund' }],
      count: 2,
    });
    renderModal();
    expect(await screen.findByText('"Login" is used by 2 tests: Checkout, Refund')).toBeInTheDocument();
    expect(screen.getByText('Steps in those tests are kept; the template link is removed.')).toBeInTheDocument();
  });

  it('loads usages for every selected template', async () => {
    apiGet.mockImplementation(async (path: string) => {
      if (path === 'templates/t1/usages') return { usages: [{ usecase_id: 'uc-1', name: 'Checkout' }], count: 1 };
      if (path === 'templates/t2/usages') return { usages: [], count: 0 };
      throw new Error(`unexpected GET ${path}`);
    });
    renderModal([LOGIN, COOKIES]);
    expect(await screen.findByText('"Login" is used by 1 test: Checkout')).toBeInTheDocument();
    expect(screen.getByText('"Cookie banner" is not used by any test.')).toBeInTheDocument();
    expect(screen.getByText('Steps in those tests are kept; the template link is removed.')).toBeInTheDocument();
  });

  it('falls back to the plain text when the usage lookup fails', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    apiGet.mockRejectedValue(new Error('boom'));
    renderModal();
    await waitFor(() => expect(error).toHaveBeenCalled());
    expect(screen.queryByText(/Checking which tests use/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/is used by|is not used by/)).not.toBeInTheDocument();
    // the delete flow itself is untouched
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
    error.mockRestore();
  });
});
