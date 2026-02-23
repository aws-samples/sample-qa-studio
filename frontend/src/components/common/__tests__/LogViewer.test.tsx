import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import LogViewer from '../LogViewer';

// Mock CodeView since it's a complex Cloudscape component
vi.mock('@cloudscape-design/code-view', () => ({
  CodeView: ({ content, lineNumbers }: { content: string; lineNumbers?: boolean }) => (
    <pre data-testid="code-view" data-line-numbers={lineNumbers}>
      {content}
    </pre>
  ),
}));

// Mock global fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('LogViewer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders loading state when loading prop is true', () => {
    const { container } = render(<LogViewer downloadUrl="https://example.com/logs.txt" loading={true} />);
    // Cloudscape Spinner renders as nested spans with circle classes
    expect(container.querySelector('[class*="circle"]')).toBeInTheDocument();
    expect(screen.queryByTestId('code-view')).not.toBeInTheDocument();
  });

  it('renders loading state when downloadUrl is null', () => {
    const { container } = render(<LogViewer downloadUrl={null} />);
    expect(container.querySelector('[class*="circle"]')).toBeInTheDocument();
    expect(screen.queryByTestId('code-view')).not.toBeInTheDocument();
  });

  it('renders loading state while fetching log content', () => {
    // fetch never resolves — stays in fetching state
    mockFetch.mockReturnValue(new Promise(() => {}));
    const { container } = render(<LogViewer downloadUrl="https://example.com/logs.txt" />);
    expect(container.querySelector('[class*="circle"]')).toBeInTheDocument();
    expect(screen.queryByTestId('code-view')).not.toBeInTheDocument();
  });

  it('renders log content in CodeView with line numbers', async () => {
    const logContent = '2024-01-15 10:30:00 - root - INFO - Suite started\n2024-01-15 10:30:01 - root - DEBUG - Step 1';
    mockFetch.mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(logContent),
    });

    render(<LogViewer downloadUrl="https://example.com/logs.txt" />);

    await waitFor(() => {
      const codeView = screen.getByTestId('code-view');
      expect(codeView).toBeInTheDocument();
      expect(codeView).toHaveTextContent('Suite started');
      expect(codeView).toHaveAttribute('data-line-numbers', 'true');
    });

    expect(mockFetch).toHaveBeenCalledWith('https://example.com/logs.txt');
  });

  it('renders error alert with retry button on fetch failure', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
    });

    render(<LogViewer downloadUrl="https://example.com/logs.txt" />);

    await waitFor(() => {
      expect(screen.getByText(/Failed to load logs/)).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('renders error alert on network error', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));

    render(<LogViewer downloadUrl="https://example.com/logs.txt" />);

    await waitFor(() => {
      expect(screen.getByText(/Network error/)).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('retry button re-fetches log content', async () => {
    // First call fails
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
    });

    render(<LogViewer downloadUrl="https://example.com/logs.txt" />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);

    // Second call succeeds
    const logContent = 'Log line 1\nLog line 2';
    mockFetch.mockResolvedValueOnce({
      ok: true,
      text: () => Promise.resolve(logContent),
    });

    await userEvent.click(screen.getByRole('button', { name: /retry/i }));

    await waitFor(() => {
      const codeView = screen.getByTestId('code-view');
      expect(codeView).toHaveTextContent('Log line 1');
    });

    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('re-fetches when downloadUrl changes', async () => {
    const logContent1 = 'First log content';
    const logContent2 = 'Second log content';

    mockFetch.mockResolvedValueOnce({
      ok: true,
      text: () => Promise.resolve(logContent1),
    });

    const { rerender } = render(<LogViewer downloadUrl="https://example.com/logs1.txt" />);

    await waitFor(() => {
      expect(screen.getByTestId('code-view')).toHaveTextContent('First log content');
    });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      text: () => Promise.resolve(logContent2),
    });

    rerender(<LogViewer downloadUrl="https://example.com/logs2.txt" />);

    await waitFor(() => {
      expect(screen.getByTestId('code-view')).toHaveTextContent('Second log content');
    });

    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('starts collapsed and toggles expand/collapse on button click', async () => {
    const logContent = 'Line 1\nLine 2\nLine 3';
    mockFetch.mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(logContent),
    });

    render(<LogViewer downloadUrl="https://example.com/logs.txt" />);

    await waitFor(() => {
      expect(screen.getByTestId('code-view')).toBeInTheDocument();
    });

    // Should start with Expand button
    const expandBtn = screen.getByRole('button', { name: /expand/i });
    expect(expandBtn).toBeInTheDocument();

    // Click to expand
    await userEvent.click(expandBtn);
    expect(screen.getByRole('button', { name: /collapse/i })).toBeInTheDocument();

    // Click to collapse
    await userEvent.click(screen.getByRole('button', { name: /collapse/i }));
    expect(screen.getByRole('button', { name: /expand/i })).toBeInTheDocument();
  });
});
