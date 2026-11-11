/**
 * ExecutionVariables — presentational Variables container of the execution panel.
 * Defined Variables = the run's snapshot (`execution_variables`), Runtime Variables =
 * values captured during the run. The panel owns the fetch; this component never calls the API.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import createWrapper from '@cloudscape-design/components/test-utils/dom';

const apiGet = vi.fn();
vi.mock('../../../utils/api', () => ({ api: { get: (...a: unknown[]) => apiGet(...a) } }));

import ExecutionVariables from '../ExecutionVariables';
import type { ExecutionVariablesResponse } from '../../../utils/api';

function response(overrides: Partial<ExecutionVariablesResponse> = {}): ExecutionVariablesResponse {
  return { variables: [], runtime_variables: [], execution_variables: {}, ...overrides };
}

const headerCounter = (container: HTMLElement) =>
  createWrapper(container).findContainer()!.findHeader()!.findHeader()!.findCounter()!.getElement().textContent?.trim();

afterEach(() => {
  cleanup();
  apiGet.mockReset();
});

describe('ExecutionVariables', () => {
  it('lists the execution snapshot as Defined Variables, not the current use-case variables', () => {
    render(
      <ExecutionVariables
        variables={response({
          variables: [{ key: 'product', value: 'Edited later' }],
          execution_variables: { product: 'Laptop', base_url: 'https://shop.test' },
        })}
      />,
    );
    expect(screen.getByText('Defined Variables')).toBeInTheDocument();
    expect(screen.getByText('product')).toBeInTheDocument();
    expect(screen.getByText('Laptop')).toBeInTheDocument();
    expect(screen.getByText('base_url')).toBeInTheDocument();
    expect(screen.getByText('https://shop.test')).toBeInTheDocument();
    expect(screen.queryByText('Edited later')).not.toBeInTheDocument();
    expect(screen.queryByText('Runtime Variables')).not.toBeInTheDocument();
  });

  it('lists runtime variables and hides Defined Variables when the snapshot is empty', () => {
    render(<ExecutionVariables variables={response({ runtime_variables: [{ key: 'order_id', value: 'A-42' }] })} />);
    expect(screen.getByText('Runtime Variables')).toBeInTheDocument();
    expect(screen.getByText('order_id')).toBeInTheDocument();
    expect(screen.getByText('A-42')).toBeInTheDocument();
    expect(screen.queryByText('Defined Variables')).not.toBeInTheDocument();
  });

  it('counts snapshot and runtime variables together in the header and per section', () => {
    const { container } = render(
      <ExecutionVariables
        variables={response({
          execution_variables: { a: '1', b: '2' },
          runtime_variables: [{ key: 'c', value: '3' }],
        })}
      />,
    );
    expect(headerCounter(container)).toBe('(3)');
    const badges = createWrapper(container).findAllBadges().map((b) => b.getElement().textContent);
    expect(badges).toEqual(['2', '1']);
  });

  it('shows an empty state when neither snapshot nor runtime variables exist', () => {
    render(<ExecutionVariables variables={response({ variables: [{ key: 'ignored', value: 'x' }] })} />);
    expect(screen.getByText('No variables defined for this execution')).toBeInTheDocument();
    expect(screen.queryByText('Defined Variables')).not.toBeInTheDocument();
    expect(screen.queryByText('Runtime Variables')).not.toBeInTheDocument();
  });

  it('never calls the API', () => {
    render(<ExecutionVariables variables={response({ execution_variables: { a: '1' } })} />);
    expect(apiGet).not.toHaveBeenCalled();
  });
});
