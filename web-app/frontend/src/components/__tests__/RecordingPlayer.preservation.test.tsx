/**
 * Preservation Property Tests
 *
 * These tests capture EXISTING correct behavior that must be preserved after
 * the bugfix. They run on UNFIXED code and MUST PASS — confirming the baseline.
 *
 * Property 2: Preservation — rrweb Playback and Button Visibility Unchanged
 *
 * **Validates: Requirements 3.1, 3.2, 3.3, 3.4**
 */
import { render, screen } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import * as fc from 'fast-check';
import React from 'react';

// ── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('../../utils/recordingUtils', () => ({
  listRecordingBatches: vi.fn(),
  getRecordingBatch: vi.fn(),
  getVideoPlayback: vi.fn(),
}));

vi.mock('rrweb-player', () => ({
  default: vi.fn(),
}));

import ExecutionInformation from '../execution/ExecutionInformation';
import { RecordingPlayer } from '../RecordingPlayer';
import { listRecordingBatches, getRecordingBatch, getVideoPlayback } from '../../utils/recordingUtils';

// ── Arbitraries ──────────────────────────────────────────────────────────────

const TERMINAL_STATUSES = ['success', 'failed', 'error', 'stopped'] as const;
const NON_TERMINAL_STATUSES = ['executing', 'pending'] as const;

/**
 * Generates a Nova Act execution with nova_session_id present and terminal status.
 * This is the non-bug-condition domain where the button should be visible on
 * both unfixed and fixed code.
 */
const novaActTerminalExecution = fc.record({
  sk: fc.constant('EXECUTION#test-exec-001'),
  status: fc.constantFrom(...TERMINAL_STATUSES),
  trigger_type: fc.constantFrom('OnDemand', 'Scheduled', 'OnDemandHeadless'),
  nova_session_id: fc.constantFrom(
    'sess-abc123',
    'sess-def456',
    'sess-ghi789',
    'sess-jkl012',
    'sess-mno345'
  ),
  created_at: fc.constant('2025-01-01T00:00:00Z'),
  starting_url: fc.constant('https://example.com'),
  executing_region: fc.constant('us-east-1'),
  region: fc.constant('us-east-1'),
});

/**
 * Generates a non-terminal execution without nova_session_id.
 * Button should be hidden on both unfixed and fixed code.
 */
const nonTerminalExecution = fc.record({
  sk: fc.constant('EXECUTION#test-exec-002'),
  status: fc.constantFrom(...NON_TERMINAL_STATUSES),
  trigger_type: fc.constantFrom('OnDemand', 'Scheduled', 'OnDemandHeadless', 'ci_runner'),
  nova_session_id: fc.constantFrom(null, '', undefined),
  created_at: fc.constant('2025-01-01T00:00:00Z'),
  starting_url: fc.constant('https://example.com'),
  executing_region: fc.constant('us-east-1'),
  region: fc.constant('us-east-1'),
});

// ── Tests ────────────────────────────────────────────────────────────────────

describe('Preservation — Button Visibility', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  /**
   * Property test 1 — Recording button removed from ExecutionInformation
   *
   * The "View" recording button has been removed from ExecutionInformation
   * as part of the execution detail UI enhancement. Recording is now in an
   * expandable section in ExecutionDetailRefactored. This test verifies
   * ExecutionInformation renders without a recording button.
   *
   * **Validates: Requirements 3.3**
   */
  it('should not show "View" button for Nova Act terminal executions (button removed)', () => {
    fc.assert(
      fc.property(novaActTerminalExecution, (execution) => {
        const { unmount } = render(
          <ExecutionInformation
            execution={execution}
            usecaseId="uc-123"
            executionId="exec-001"
          />
        );

        // Recording button was removed — recording is now in an expandable section
        const viewButton = screen.queryByRole('button', { name: /view/i });
        expect(viewButton).not.toBeInTheDocument();

        unmount();
      }),
      { numRuns: 20 }
    );
  });

  /**
   * Property test 2 — Button hidden for non-terminal executions
   *
   * Recording button has been removed from ExecutionInformation entirely.
   * This test verifies no "View" button appears for non-terminal executions.
   *
   * **Validates: Requirements 3.3**
   */
  it('should hide "View" button for non-terminal executions without nova_session_id', () => {
    fc.assert(
      fc.property(nonTerminalExecution, (execution) => {
        const { unmount } = render(
          <ExecutionInformation
            execution={execution}
            usecaseId="uc-123"
            executionId="exec-001"
          />
        );

        const viewButton = screen.queryByRole('button', { name: /view/i });
        expect(viewButton).not.toBeInTheDocument();

        unmount();
      }),
      { numRuns: 20 }
    );
  });
});


describe('Preservation — rrweb Player Path', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  /**
   * Property test 3 — rrweb player path
   *
   * On UNFIXED code, RecordingPlayer always calls listRecordingBatches directly
   * (it doesn't know about getVideoPlayback). When batches are returned, the
   * component proceeds with rrweb loading and does NOT render a <video> element.
   *
   * After the fix, when /video returns playback_type: "rrweb", the component
   * should still call listRecordingBatches and NOT render <video>.
   *
   * This test verifies the rrweb path works correctly on both unfixed and fixed code.
   *
   * **Validates: Requirements 3.1, 3.4**
   */
  it('should call listRecordingBatches and not render <video> for rrweb recordings', async () => {
    const batchIds = ['batch-001', 'batch-002'];

    vi.mocked(getVideoPlayback).mockResolvedValue({
      playback_type: 'rrweb',
      execution_id: 'exec-001',
      trigger_type: 'OnDemand',
      batches: batchIds,
      metadata: {
        startTime: '2025-01-01T00:00:00Z',
        duration: 60,
        eventCount: 100,
      },
    });

    vi.mocked(listRecordingBatches).mockResolvedValue({
      batches: batchIds,
      metadata: {
        startTime: '2025-01-01T00:00:00Z',
        duration: 60,
        eventCount: 100,
      },
    });

    vi.mocked(getRecordingBatch).mockResolvedValue({
      events: [
        { type: 4, timestamp: 1000, data: { tag: 'body' } },
        { type: 3, timestamp: 2000, data: {} },
      ],
      totalCount: 2,
      totalPages: 1,
      page: 1,
      pageSize: 200,
      hasMore: false,
    });

    render(
      <RecordingPlayer
        usecaseId="uc-123"
        executionId="exec-001"
      />
    );

    // Wait for listRecordingBatches to be called
    await vi.waitFor(
      () => {
        expect(listRecordingBatches).toHaveBeenCalledWith('uc-123', 'exec-001');
      },
      { timeout: 3000 }
    );

    // Verify no <video> element is rendered
    const videoElement = document.querySelector('video');
    expect(videoElement).not.toBeInTheDocument();
  });
});

describe('Preservation — 404 Error Handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  /**
   * Property test 4 — 404 error handling
   *
   * On UNFIXED code, when listRecordingBatches returns empty batches (the
   * equivalent of "no recording available"), the component shows an error alert.
   *
   * After the fix, when /video returns 404, the component should also show an
   * error. This test verifies error display works on both unfixed and fixed code.
   *
   * **Validates: Requirements 3.2**
   */
  it('should display error alert when no recording batches are found', async () => {
    vi.mocked(getVideoPlayback).mockRejectedValue(new Error('No recording found'));

    vi.mocked(listRecordingBatches).mockResolvedValue({
      batches: [],
      metadata: {},
    });

    render(
      <RecordingPlayer
        usecaseId="uc-123"
        executionId="exec-001"
      />
    );

    // Wait for the error alert to appear
    await vi.waitFor(
      () => {
        const alert = screen.getByText(/no recording found/i);
        expect(alert).toBeInTheDocument();
      },
      { timeout: 3000 }
    );
  });
});
