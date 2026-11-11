/**
 * useCosts: one request per id, 403/404 → hidden, other failures → error
 * message, stale answers after an id change are dropped.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import { useCosts } from '../useCosts';

const loader = vi.fn();

function Probe({ id }: { id: string }) {
  const { data, loading, error, hidden } = useCosts<{ value: string }>(loader, id);
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="hidden">{String(hidden)}</span>
      <span data-testid="error">{error ?? ''}</span>
      <span data-testid="data">{data?.value ?? ''}</span>
    </div>
  );
}

function httpError(status: number, message = `HTTP ${status}`) {
  const err = new Error(message);
  (err as Error & { status: number }).status = status;
  return err;
}

beforeEach(() => {
  loader.mockReset();
});

describe('useCosts', () => {
  it('starts loading and exposes the data once the loader resolves', async () => {
    loader.mockResolvedValue({ value: 'ok' });
    render(<Probe id="a" />);
    expect(screen.getByTestId('loading').textContent).toBe('true');
    await waitFor(() => expect(screen.getByTestId('data').textContent).toBe('ok'));
    expect(screen.getByTestId('loading').textContent).toBe('false');
    expect(screen.getByTestId('hidden').textContent).toBe('false');
    expect(screen.getByTestId('error').textContent).toBe('');
    expect(loader).toHaveBeenCalledTimes(1);
    expect(loader).toHaveBeenCalledWith('a');
  });

  it.each([403, 404])('marks the card hidden on %s without an error message', async (status) => {
    loader.mockRejectedValue(httpError(status));
    render(<Probe id="a" />);
    await waitFor(() => expect(screen.getByTestId('hidden').textContent).toBe('true'));
    expect(screen.getByTestId('loading').textContent).toBe('false');
    expect(screen.getByTestId('error').textContent).toBe('');
  });

  it('surfaces other failures as an error message and stays visible', async () => {
    loader.mockRejectedValue(httpError(500, 'Internal Server Error'));
    render(<Probe id="a" />);
    await waitFor(() => expect(screen.getByTestId('error').textContent).toBe('Internal Server Error'));
    expect(screen.getByTestId('hidden').textContent).toBe('false');
    expect(screen.getByTestId('loading').textContent).toBe('false');
  });

  it('falls back to a generic message for a non-Error rejection', async () => {
    loader.mockRejectedValue('boom');
    render(<Probe id="a" />);
    await waitFor(() => expect(screen.getByTestId('error').textContent).toBe('Failed to load cost data'));
  });

  it('does not refetch on re-render with the same id', async () => {
    loader.mockResolvedValue({ value: 'ok' });
    const { rerender } = render(<Probe id="a" />);
    await waitFor(() => expect(screen.getByTestId('data').textContent).toBe('ok'));
    rerender(<Probe id="a" />);
    expect(loader).toHaveBeenCalledTimes(1);
  });

  it('refetches when the id changes and ignores the stale answer', async () => {
    let resolveA: (v: { value: string }) => void = () => undefined;
    loader.mockImplementation((id: string) => {
      if (id === 'a') return new Promise<{ value: string }>((resolve) => { resolveA = resolve; });
      return Promise.resolve({ value: 'b-data' });
    });
    const { rerender } = render(<Probe id="a" />);
    rerender(<Probe id="b" />);
    await waitFor(() => expect(screen.getByTestId('data').textContent).toBe('b-data'));
    await act(async () => { resolveA({ value: 'a-data' }); });
    expect(screen.getByTestId('data').textContent).toBe('b-data');
    expect(loader).toHaveBeenCalledTimes(2);
  });
});
