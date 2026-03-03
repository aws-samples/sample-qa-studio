import React from 'react';
import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import StepsTable from '../StepsTable';

// Mock the API module
vi.mock('../../utils/api', () => ({
  api: {
    patch: vi.fn(),
  },
}));

// Mock StepFormModal
vi.mock('../usecase/StepFormModal', () => {
  return {
    default: function MockStepFormModal() {
      return <div data-testid="step-form-modal">Mock Step Form Modal</div>;
    }
  };
});

describe('StepsTable - Cache Indicators', () => {
  const mockOnStepsReordered = vi.fn();
  const mockOnUpdateStep = vi.fn();
  const mockOnDeleteStep = vi.fn();
  const usecaseId = 'test-usecase-123';

  const createStep = (overrides = {}) => ({
    pk: 'USECASE#test-usecase-123',
    sk: 'STEP#step-1',
    usecaseId: 'test-usecase-123',
    sort: 1,
    instruction: 'Click login button',
    step_type: 'navigation',
    ...overrides,
  });

  it('should display cache badge for navigation steps with cached_steps', () => {
    const steps = [
      createStep({
        cached_steps: '[{"type":"click","bbox":{"x1":100,"y1":200,"x2":300,"y2":400}}]',
        cache_last_updated: '2026-03-03T10:00:00Z',
      }),
    ];

    render(
      <StepsTable
        steps={steps}
        onStepsReordered={mockOnStepsReordered}
        onUpdateStep={mockOnUpdateStep}
        onDeleteStep={mockOnDeleteStep}
        usecaseId={usecaseId}
      />
    );

    expect(screen.getByText('Cached')).toBeInTheDocument();
  });

  it('should NOT display cache badge for navigation steps without cached_steps', () => {
    const steps = [
      createStep({
        cached_steps: null,
        cache_last_updated: null,
      }),
    ];

    render(
      <StepsTable
        steps={steps}
        onStepsReordered={mockOnStepsReordered}
        onUpdateStep={mockOnUpdateStep}
        onDeleteStep={mockOnDeleteStep}
        usecaseId={usecaseId}
      />
    );

    expect(screen.queryByText('Cached')).not.toBeInTheDocument();
  });

  it('should NOT display cache badge for non-navigation steps', () => {
    const steps = [
      createStep({
        step_type: 'validation',
        cached_steps: '[{"type":"click"}]',
        cache_last_updated: '2026-03-03T10:00:00Z',
      }),
    ];

    render(
      <StepsTable
        steps={steps}
        onStepsReordered={mockOnStepsReordered}
        onUpdateStep={mockOnUpdateStep}
        onDeleteStep={mockOnDeleteStep}
        usecaseId={usecaseId}
      />
    );

    expect(screen.queryByText('Cached')).not.toBeInTheDocument();
  });

  it('should display cache age in step details', () => {
    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    const steps = [
      createStep({
        cached_steps: '[{"type":"click"}]',
        cache_last_updated: oneHourAgo,
      }),
    ];

    render(
      <StepsTable
        steps={steps}
        onStepsReordered={mockOnStepsReordered}
        onUpdateStep={mockOnUpdateStep}
        onDeleteStep={mockOnDeleteStep}
        usecaseId={usecaseId}
      />
    );

    expect(screen.getByText(/Cached 1 hour ago/)).toBeInTheDocument();
  });

  it('should display "just now" for very recent cache', () => {
    const justNow = new Date(Date.now() - 10 * 1000).toISOString();
    const steps = [
      createStep({
        cached_steps: '[{"type":"click"}]',
        cache_last_updated: justNow,
      }),
    ];

    render(
      <StepsTable
        steps={steps}
        onStepsReordered={mockOnStepsReordered}
        onUpdateStep={mockOnUpdateStep}
        onDeleteStep={mockOnDeleteStep}
        usecaseId={usecaseId}
      />
    );

    expect(screen.getByText(/Cached just now/)).toBeInTheDocument();
  });
});
