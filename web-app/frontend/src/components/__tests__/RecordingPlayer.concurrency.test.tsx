import { act, cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { TEST_CONCURRENCY } = vi.hoisted(() => ({ TEST_CONCURRENCY: 3 }));

vi.mock('../../utils/recordingUtils', () => ({
  getRecordingBatch: vi.fn(),
  getVideoPlayback: vi.fn(),
  listRecordingBatches: vi.fn(),
}));

vi.mock('../../utils/batchedPromiseAll', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../utils/batchedPromiseAll')>(),
  getEffectiveBatchSize: vi.fn(() => TEST_CONCURRENCY),
}));

vi.mock('rrweb-player', () => ({
  default: vi.fn(function () {
    return {
      $destroy: vi.fn(),
      getCurrentTime: vi.fn(() => 0),
    };
  }),
}));

import { RecordingPlayer } from '../RecordingPlayer';
import {
  getRecordingBatch,
  getVideoPlayback,
  listRecordingBatches,
  type RecordingBatch,
} from '../../utils/recordingUtils';

function batchPage(page: number, totalPages: number): RecordingBatch {
  return {
    events: [{ type: 4, timestamp: page, data: {} }],
    totalCount: totalPages,
    totalPages,
    page,
    pageSize: 200,
    hasMore: page < totalPages,
  };
}

type PendingPage = {
  page: number;
  resolve: (value: RecordingBatch) => void;
};

function resolvePending(pending: PendingPage[], totalPages: number): void {
  pending.splice(0).forEach(({ page, resolve }) => resolve(batchPage(page, totalPages)));
}

describe('RecordingPlayer batch concurrency', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.mocked(getVideoPlayback).mockResolvedValue({
      playback_type: 'rrweb',
      execution_id: 'execution-1',
      trigger_type: 'OnDemandHeadless',
      batches: ['batch-1'],
      metadata: {},
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('limits initial recording pages to the configured Lambda concurrency', async () => {
    const totalPages = TEST_CONCURRENCY + 2;
    const pending: PendingPage[] = [];

    vi.mocked(listRecordingBatches).mockResolvedValue({ batches: ['batch-1'], metadata: {} });
    vi.mocked(getRecordingBatch).mockImplementation(
      async (_usecaseId, _executionId, _batchId, page = 1) => {
        if (page === 1) return batchPage(page, totalPages);
        return new Promise<RecordingBatch>((resolve) => pending.push({ page, resolve }));
      },
    );

    const { unmount } = render(<RecordingPlayer usecaseId="usecase-1" executionId="execution-1" />);

    await waitFor(() => {
      expect(getRecordingBatch).toHaveBeenCalledTimes(TEST_CONCURRENCY + 1);
    });
    expect(vi.mocked(getRecordingBatch).mock.calls.some((call) => call[3] === totalPages)).toBe(false);

    await act(async () => {
      resolvePending(pending, totalPages);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(getRecordingBatch).toHaveBeenCalledWith(
        'usecase-1',
        'execution-1',
        'batch-1',
        totalPages,
      );
    });

    await act(async () => {
      resolvePending(pending, totalPages);
      await Promise.resolve();
    });
    unmount();
  });

  it('limits background recording pages to the configured Lambda concurrency', async () => {
    const totalPages = TEST_CONCURRENCY + 2;
    const pending: PendingPage[] = [];

    vi.mocked(listRecordingBatches).mockResolvedValue({
      batches: ['batch-1', 'batch-2'],
      metadata: {},
    });
    vi.mocked(getRecordingBatch).mockImplementation(
      async (_usecaseId, _executionId, batchId, page = 1) => {
        if (batchId === 'batch-1') return batchPage(page, 1);
        if (page === 1) return batchPage(page, totalPages);
        return new Promise<RecordingBatch>((resolve) => pending.push({ page, resolve }));
      },
    );

    const { unmount } = render(<RecordingPlayer usecaseId="usecase-1" executionId="execution-1" />);

    await waitFor(() => {
      const backgroundCalls = vi.mocked(getRecordingBatch).mock.calls.filter(
        (call) => call[2] === 'batch-2',
      );
      expect(backgroundCalls).toHaveLength(TEST_CONCURRENCY + 1);
    });
    expect(
      vi.mocked(getRecordingBatch).mock.calls.some(
        (call) => call[2] === 'batch-2' && call[3] === totalPages,
      ),
    ).toBe(false);

    await act(async () => {
      resolvePending(pending, totalPages);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(getRecordingBatch).toHaveBeenCalledWith(
        'usecase-1',
        'execution-1',
        'batch-2',
        totalPages,
      );
    });

    await act(async () => {
      resolvePending(pending, totalPages);
      await Promise.resolve();
    });
    unmount();
  });
});
