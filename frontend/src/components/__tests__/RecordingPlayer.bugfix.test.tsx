/**
 * Bug Condition Exploration Tests
 *
 * These tests encode the EXPECTED (correct) behavior for CI runner executions.
 * On UNFIXED code they MUST FAIL — failure confirms the bug exists.
 *
 * Bug 1.2: "View" button is gated on `nova_session_id`, hiding it for CI runner
 *          executions that have video recordings but no Nova session.
 * Bug 1.3: `RecordingPlayer` unconditionally calls `listRecordingBatches` (rrweb path)
 *          instead of calling `getVideoPlayback` and branching to HTML5 `<video>`.
 *
 * **Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2, 2.3**
 */
import { render, screen } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as fc from 'fast-check';
import React from 'react';

// ── Mocks ────────────────────────────────────────────────────────────────────

// Mock the recording utils module — getVideoPlayback does NOT exist yet in the
// source, so we define it here as a mock for the expected future API.
vi.mock('../../utils/recordingUtils', () => ({
  listRecordingBatches: vi.fn(),
  getRecordingBatch: vi.fn(),
  getVideoPlayback: vi.fn(),
}));

// Mock rrweb-player dynamic import so it doesn't break in jsdom
vi.mock('rrweb-player', () => ({
  default: vi.fn(),
}));

import ExecutionInformation from '../execution/ExecutionInformation';
import { RecordingPlayer } from '../RecordingPlayer';
import { listRecordingBatches, getRecordingBatch } from '../../utils/recordingUtils';

// We import getVideoPlayback from the mock — it won't exist in the real module
// until Task 3.1, but the mock provides it.
const { getVideoPlayback } = await import('../../utils/recordingUtils') as any;

// ── Arbitraries ──────────────────────────────────────────────────────────────

const TERMINAL_STATUSES = ['success', 'failed', 'error', 'stopped'] as const;

/**
 * Generates a CI runner execution object with a terminal status and NO
 * nova_session_id — the exact input domain where the bug manifests.
 */
const ciRunnerTerminalExecution = fc.record({
  sk: fc.constant('EXECUTION#test-exec-001'),
  status: fc.constantFrom(...TERMINAL_STATUSES),
  trigger_type: fc.constant('ci_runner'),
  nova_session_id: fc.constantFrom(null, '', undefined),
  created_at: fc.constant('2025-01-01T00:00:00Z'),
  starting_url: fc.constant('https://example.com'),
  executing_region: fc.constant('us-east-1'),
  region: fc.constant('us-east-1'),
});

// ── Tests ────────────────────────────────────────────────────────────────────

describe('Bug Condition Exploration — CI Runner Recordings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  /**
   * Test 1 — Button visibility (Bug 1.2)
   *
   * For any CI runner execution with a terminal status and no nova_session_id,
   * the "View" button SHOULD be visible (expected behavior).
   *
   * On UNFIXED code the button is gated on `execution.nova_session_id`, so it
   * will NOT render → test fails → confirms the bug.
   */
  it('should show "View" button for terminal CI runner executions without nova_session_id', () => {
    fc.assert(
      fc.property(ciRunnerTerminalExecution, (execution) => {
        const { unmount } = render(
          <ExecutionInformation
            execution={execution}
            usecaseId="uc-123"
            executionId="exec-001"
            onViewRecording={() => {}}
          />
        );

        // Expected behavior: button is visible for any terminal execution
        const viewButton = screen.queryByRole('button', { name: /view/i });
        expect(viewButton).toBeInTheDocument();

        unmount();
      }),
      { numRuns: 20 }
    );
  });

  /**
   * Test 2 — Player branch (Bug 1.3)
   *
   * When `getVideoPlayback` returns `playback_type: "video"` with a
   * `download_url`, the RecordingPlayer SHOULD render a `<video>` element.
   *
   * On UNFIXED code, RecordingPlayer ignores `getVideoPlayback` entirely and
   * calls `listRecordingBatches` instead → no `<video>` element → test fails
   * → confirms the bug.
   */
  it('should render <video> element when getVideoPlayback returns playback_type "video"', async () => {
    // Mock getVideoPlayback to return a video playback response
    vi.mocked(getVideoPlayback).mockResolvedValue({
      playback_type: 'video',
      execution_id: 'exec-001',
      trigger_type: 'ci_runner',
      download_url: 'https://example.com/recording.webm',
      content_type: 'video/webm',
      expires_in: 3600,
    });

    // Mock listRecordingBatches to return empty (CI runner has no rrweb batches)
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

    // Wait for async operations to settle
    // The component should call getVideoPlayback and render a <video> element
    await vi.waitFor(
      () => {
        const videoElement = document.querySelector('video');
        expect(videoElement).toBeInTheDocument();
        expect(videoElement?.getAttribute('src')).toBe(
          'https://example.com/recording.webm'
        );
      },
      { timeout: 3000 }
    );
  });
});
