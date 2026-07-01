import React from 'react';
import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import StepsTable from '../StepsTable';

vi.mock('../../utils/api', () => ({
  api: {
    patch: vi.fn(),
  },
}));

vi.mock('../usecase/StepFormModal', () => ({
  default: function MockStepFormModal() {
    return <div data-testid="step-form-modal">Mock Step Form Modal</div>;
  }
}));

describe('StepsTable — network_assertion rendering', () => {
  const mockOnStepsReordered = vi.fn();
  const mockOnUpdateStep = vi.fn();
  const mockOnDeleteStep = vi.fn();
  const usecaseId = 'test-usecase-123';

  const createNetworkStep = (overrides = {}) => ({
    pk: 'USECASE#test-usecase-123',
    sk: 'STEP#step-1',
    usecaseId: 'test-usecase-123',
    sort: 1,
    instruction: 'Click submit',
    step_type: 'network_assertion',
    network_url_pattern: '**/api/users',
    network_method: 'POST',
    ...overrides,
  });

  it('shows a Network badge', () => {
    render(
      <StepsTable
        steps={[createNetworkStep()]}
        onStepsReordered={mockOnStepsReordered}
        onUpdateStep={mockOnUpdateStep}
        onDeleteStep={mockOnDeleteStep}
        usecaseId={usecaseId}
      />
    );
    expect(screen.getByText('Network')).toBeInTheDocument();
  });

  it('shows the URL pattern and method in the summary', () => {
    render(
      <StepsTable
        steps={[createNetworkStep()]}
        onStepsReordered={mockOnStepsReordered}
        onUpdateStep={mockOnUpdateStep}
        onDeleteStep={mockOnDeleteStep}
        usecaseId={usecaseId}
      />
    );
    expect(screen.getByText(/Network: POST \*\*\/api\/users/)).toBeInTheDocument();
  });

  it('indicates a static mock', () => {
    render(
      <StepsTable
        steps={[
          createNetworkStep({
            network_mock_response: '{"status":201}',
            network_mock_passthrough: false,
          }),
        ]}
        onStepsReordered={mockOnStepsReordered}
        onUpdateStep={mockOnUpdateStep}
        onDeleteStep={mockOnDeleteStep}
        usecaseId={usecaseId}
      />
    );
    expect(screen.getByText(/static mock/)).toBeInTheDocument();
  });

  it('indicates a passthrough mock when enabled', () => {
    render(
      <StepsTable
        steps={[
          createNetworkStep({
            network_mock_response: '{"status":201}',
            network_mock_passthrough: true,
          }),
        ]}
        onStepsReordered={mockOnStepsReordered}
        onUpdateStep={mockOnUpdateStep}
        onDeleteStep={mockOnDeleteStep}
        usecaseId={usecaseId}
      />
    );
    expect(screen.getByText(/passthrough mock/)).toBeInTheDocument();
  });

  it('uses "any" method when none is configured', () => {
    render(
      <StepsTable
        steps={[createNetworkStep({ network_method: null })]}
        onStepsReordered={mockOnStepsReordered}
        onUpdateStep={mockOnUpdateStep}
        onDeleteStep={mockOnDeleteStep}
        usecaseId={usecaseId}
      />
    );
    expect(screen.getByText(/Network: any/)).toBeInTheDocument();
  });
});

describe('StepsTable — network_assertion response-side rendering', () => {
  const mockOnStepsReordered = vi.fn();
  const mockOnUpdateStep = vi.fn();
  const mockOnDeleteStep = vi.fn();
  const usecaseId = 'test-usecase-123';

  const createNetworkStep = (overrides = {}) => ({
    pk: 'USECASE#test-usecase-123',
    sk: 'STEP#step-1',
    usecaseId: 'test-usecase-123',
    sort: 1,
    instruction: 'Click submit',
    step_type: 'network_assertion',
    network_url_pattern: '**/api/users',
    network_method: 'POST',
    ...overrides,
  });

  it('shows the expected response status when set', () => {
    render(
      <StepsTable
        steps={[createNetworkStep({ network_response_status: 201 })]}
        onStepsReordered={mockOnStepsReordered}
        onUpdateStep={mockOnUpdateStep}
        onDeleteStep={mockOnDeleteStep}
        usecaseId={usecaseId}
      />
    );
    expect(screen.getByText(/resp 201/)).toBeInTheDocument();
  });

  it('shows the response body match type when set', () => {
    render(
      <StepsTable
        steps={[
          createNetworkStep({
            network_response_body: '{"type":"object"}',
            network_response_body_match_type: 'schema',
          }),
        ]}
        onStepsReordered={mockOnStepsReordered}
        onUpdateStep={mockOnUpdateStep}
        onDeleteStep={mockOnDeleteStep}
        usecaseId={usecaseId}
      />
    );
    expect(screen.getByText(/resp body \(schema\)/)).toBeInTheDocument();
  });

  it('defaults response body match type label to "subset" when not explicitly set', () => {
    render(
      <StepsTable
        steps={[
          createNetworkStep({
            network_response_body: '{"id":"x"}',
            // no explicit match type
          }),
        ]}
        onStepsReordered={mockOnStepsReordered}
        onUpdateStep={mockOnUpdateStep}
        onDeleteStep={mockOnDeleteStep}
        usecaseId={usecaseId}
      />
    );
    expect(screen.getByText(/resp body \(subset\)/)).toBeInTheDocument();
  });

  it('renders request and response segments together without colliding', () => {
    render(
      <StepsTable
        steps={[
          createNetworkStep({
            network_request_body: '{"name":"John"}',
            network_body_match_type: 'subset',
            network_response_status: 200,
            network_response_body: '{"id":"x"}',
            network_response_body_match_type: 'schema',
          }),
        ]}
        onStepsReordered={mockOnStepsReordered}
        onUpdateStep={mockOnUpdateStep}
        onDeleteStep={mockOnDeleteStep}
        usecaseId={usecaseId}
      />
    );
    expect(screen.getByText(/req body \(subset\)/)).toBeInTheDocument();
    expect(screen.getByText(/resp 200/)).toBeInTheDocument();
    expect(screen.getByText(/resp body \(schema\)/)).toBeInTheDocument();
  });

  it('omits response segments when no response assertion is set', () => {
    render(
      <StepsTable
        steps={[createNetworkStep()]}
        onStepsReordered={mockOnStepsReordered}
        onUpdateStep={mockOnUpdateStep}
        onDeleteStep={mockOnDeleteStep}
        usecaseId={usecaseId}
      />
    );
    // no resp * markers should be present
    expect(screen.queryByText(/resp \d+/)).not.toBeInTheDocument();
    expect(screen.queryByText(/resp body/)).not.toBeInTheDocument();
  });
});
