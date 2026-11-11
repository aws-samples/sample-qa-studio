import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import UsecaseHooks from '../UsecaseHooks';

const hooksGet = vi.fn();
const hooksCreate = vi.fn();

vi.mock('../../../utils/api', () => ({
  hooksApi: {
    get: (...a: unknown[]) => hooksGet(...a),
    create: (...a: unknown[]) => hooksCreate(...a),
  },
}));

// The real editor is ace inside a lazy chunk; a textarea keeps the test about UsecaseHooks.
vi.mock('../../common/LazyCodeEditor', () => ({
  default: ({ value, onChange }: { value: string; onChange: (e: { detail: { value: string } }) => void }) => (
    <textarea
      data-testid="code-editor"
      value={value}
      onChange={(e) => onChange({ detail: { value: e.target.value } })}
    />
  ),
}));

describe('UsecaseHooks', () => {
  beforeEach(() => {
    hooksGet.mockReset();
    hooksCreate.mockReset();
  });
  afterEach(() => {
    cleanup();
  });

  it('loads the hooks through hooksApi.get', async () => {
    hooksGet.mockResolvedValue({ before_script: 'print("a")', after_script: '' });

    render(<UsecaseHooks usecaseId="u-1" />);

    await waitFor(() => expect(hooksGet).toHaveBeenCalledWith('u-1'));
    const editors = await screen.findAllByTestId('code-editor');
    expect((editors[0] as HTMLTextAreaElement).value).toBe('print("a")');
    expect(screen.getByRole('button', { name: 'Saved' })).toBeDisabled();
  });

  it('saves edited hooks through hooksApi.create', async () => {
    hooksGet.mockResolvedValue({ before_script: '', after_script: '' });
    hooksCreate.mockResolvedValue({});

    render(<UsecaseHooks usecaseId="u-1" />);
    const [before] = await screen.findAllByTestId('code-editor');
    fireEvent.change(before, { target: { value: 'setup()' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));

    await waitFor(() =>
      expect(hooksCreate).toHaveBeenCalledWith('u-1', { before_script: 'setup()', after_script: '' }),
    );
    expect(await screen.findByRole('button', { name: 'Saved' })).toBeDisabled();
  });

  it('treats a 404 as "no hooks yet" and shows no error', async () => {
    hooksGet.mockRejectedValue({ status: 404 });

    render(<UsecaseHooks usecaseId="u-1" />);

    expect(await screen.findAllByTestId('code-editor')).toHaveLength(2);
    expect(screen.queryByText('Failed to load hooks')).not.toBeInTheDocument();
  });

  it('shows an error when saving fails', async () => {
    hooksGet.mockResolvedValue({ before_script: '', after_script: '' });
    hooksCreate.mockRejectedValue(new Error('boom'));

    render(<UsecaseHooks usecaseId="u-1" />);
    const [before] = await screen.findAllByTestId('code-editor');
    fireEvent.change(before, { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));

    expect(await screen.findByText('Failed to save hooks. Please try again.')).toBeInTheDocument();
  });
});
