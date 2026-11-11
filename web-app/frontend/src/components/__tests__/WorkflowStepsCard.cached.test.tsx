/**
 * WorkflowStepsCard — Cached (trajectory replay) indicators: the green badge
 * next to the step type and the "Cached <time ago>" detail line.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';

import WorkflowStepsCard from '../WorkflowStepsCard';

vi.mock('../../utils/api', () => ({ api: { patch: vi.fn() } }));
vi.mock('../usecase/StepFormModal', () => ({ default: () => null }));

afterEach(() => cleanup());

const createStep = (overrides: Record<string, unknown> = {}) => ({
  pk: 'USECASE#test-usecase-123',
  sk: 'STEP#step-1',
  id: 'step-1',
  usecaseId: 'test-usecase-123',
  sort: 1,
  instruction: 'Click login button',
  step_type: 'navigation',
  ...overrides,
});

function renderCards(steps: ReturnType<typeof createStep>[]) {
  render(
    <WorkflowStepsCard
      steps={steps as any}
      onReorder={vi.fn()}
      onUpdateStep={vi.fn()}
      onDeleteStep={vi.fn()}
      onAddStep={vi.fn()}
      usecaseId="test-usecase-123"
    />,
  );
}

describe('WorkflowStepsCard — Cached (trajectory replay) indicators', () => {
  it('shows the Cached badge on the card of a navigation step with a recorded trajectory', () => {
    renderCards([createStep({
      trajectory_s3_key: 'trajectories/u/step-1.json',
      trajectory_last_updated: '2026-03-03T10:00:00Z',
    })]);

    const card = screen.getByTestId('step-card');
    expect(within(card).getByText('Cached')).toBeInTheDocument();
  });

  it('places the badge right after the step type badge', () => {
    renderCards([createStep({ trajectory_s3_key: 'k' })]);

    const typeBadge = screen.getByText('Navigation');
    const cached = screen.getByText('Cached');
    // Both badges sit in the same badge row, type first.
    const row = typeBadge.closest('div[style*="gap"]');
    expect(row).not.toBeNull();
    expect(row).toContainElement(cached);
    expect(typeBadge.compareDocumentPosition(cached) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('treats a step without step_type as navigation', () => {
    renderCards([createStep({ step_type: undefined, trajectory_s3_key: 'k' })]);

    expect(screen.getByText('Cached')).toBeInTheDocument();
  });

  it('hides the badge without a trajectory', () => {
    renderCards([createStep({ trajectory_s3_key: null, trajectory_last_updated: null })]);

    expect(screen.queryByText('Cached')).not.toBeInTheDocument();
  });

  it('hides the badge for a step that only has the legacy bbox cached_steps', () => {
    renderCards([createStep({
      cached_steps: '[{"type":"click","bbox":{"x1":100,"y1":200,"x2":300,"y2":400}}]',
      cache_last_updated: '2026-03-03T10:00:00Z',
    })]);

    expect(screen.queryByText('Cached')).not.toBeInTheDocument();
    expect(screen.queryByText(/^Cached /)).not.toBeInTheDocument();
  });

  it('hides the badge and the age line for non-navigation steps (only navigation records trajectories)', () => {
    renderCards([createStep({
      step_type: 'validation',
      validation_type: 'string',
      validation_value: 'x',
      trajectory_s3_key: 'k',
      trajectory_last_updated: '2026-03-03T10:00:00Z',
    })]);

    expect(screen.queryByText('Cached')).not.toBeInTheDocument();
    expect(screen.queryByText(/^Cached /)).not.toBeInTheDocument();
  });

  it('ends the step details with the trajectory age', () => {
    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    renderCards([createStep({ trajectory_s3_key: 'k', trajectory_last_updated: oneHourAgo })]);

    const age = screen.getByText('Cached 1h ago');
    expect(age.parentElement).toHaveClass('step-details');
    expect(age.nextElementSibling).toBeNull();
  });

  it('shows "just now" for a trajectory recorded seconds ago', () => {
    const justNow = new Date(Date.now() - 10 * 1000).toISOString();
    renderCards([createStep({ trajectory_s3_key: 'k', trajectory_last_updated: justNow })]);

    expect(screen.getByText('Cached just now')).toBeInTheDocument();
  });

  it('shows the badge but no age line when the trajectory has no timestamp', () => {
    renderCards([createStep({ trajectory_s3_key: 'k', trajectory_last_updated: null })]);

    expect(screen.getByText('Cached')).toBeInTheDocument();
    expect(screen.queryByText(/^Cached /)).not.toBeInTheDocument();
  });
});
