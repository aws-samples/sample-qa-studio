/**
 * WorkflowStepsCard — network_assertion cards: type badge and the summary
 * line. The response-side segments come from stepDetailLines and are pinned
 * in stepDetails tests.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';

import WorkflowStepsCard from '../WorkflowStepsCard';

vi.mock('../../utils/api', () => ({ api: { patch: vi.fn() } }));
vi.mock('../usecase/StepFormModal', () => ({ default: () => null }));

afterEach(() => cleanup());

const createNetworkStep = (overrides: Record<string, unknown> = {}) => ({
  pk: 'USECASE#test-usecase-123',
  sk: 'STEP#step-1',
  id: 'step-1',
  usecaseId: 'test-usecase-123',
  sort: 1,
  instruction: 'Click submit',
  step_type: 'network_assertion',
  network_url_pattern: '**/api/users',
  network_method: 'POST',
  ...overrides,
});

function renderCards(steps: ReturnType<typeof createNetworkStep>[]) {
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

describe('WorkflowStepsCard — network_assertion rendering', () => {
  it('shows a Network badge', () => {
    renderCards([createNetworkStep()]);
    expect(within(screen.getByTestId('step-card')).getByText('Network')).toBeInTheDocument();
  });

  it('shows the URL pattern and method in the summary', () => {
    renderCards([createNetworkStep()]);
    expect(screen.getByText(/Network: POST \*\*\/api\/users/)).toBeInTheDocument();
  });

  it('indicates a static mock', () => {
    renderCards([createNetworkStep({ network_mock_response: '{"status":201}', network_mock_passthrough: false })]);
    expect(screen.getByText(/static mock/)).toBeInTheDocument();
  });
});
