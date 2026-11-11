/**
 * The detail lines of every step type on the step cards (WorkflowStepsCard).
 * The cards read stepDetailLines; these tests pin the card-specific parts
 * (instruction, assertion variable).
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

vi.mock('../../utils/api', () => ({ api: { patch: vi.fn() } }));
vi.mock('../usecase/StepFormModal', () => ({ default: () => null }));

import WorkflowStepsCard from '../WorkflowStepsCard';

afterEach(() => cleanup());

const step = (extra: Record<string, unknown>) => ({
  pk: 'USECASE#u',
  sk: 'STEP#s1',
  id: 's1',
  usecaseId: 'u',
  sort: 1,
  instruction: 'Do the thing',
  ...extra,
});

function renderCards(steps: Record<string, unknown>[]) {
  render(
    <WorkflowStepsCard
      steps={steps as any}
      onReorder={vi.fn()}
      onUpdateStep={vi.fn()}
      onDeleteStep={vi.fn()}
      onAddStep={vi.fn()}
      usecaseId="u"
    />,
  );
}

/** Steps and the type lines their card shows. */
const TYPE_LINE_CASES: [string, Record<string, unknown>, string[]][] = [
  ['secret', { step_type: 'secret', secret_key: 'password' }, ['Secret: password']],
  [
    'validation',
    { step_type: 'validation', validation_type: 'string', validation_operator: 'contains', validation_value: 'Hi' },
    ['Validation: Text contains "Hi"'],
  ],
  ['retrieve_value', { step_type: 'retrieve_value', capture_variable: 'order_id' }, ['Captures variable: order_id']],
  ['browser', { step_type: 'browser', browser_action: 'reload', browser_args: '{"hard": true}' }, ['Action: reload', 'Hard reload']],
  ['transform', { step_type: 'transform', transform_operation: 'uppercase', capture_variable: 'n' }, ['Operation: uppercase', '→ {{ n }}']],
  [
    'network_assertion',
    { step_type: 'network_assertion', network_method: 'GET', network_url_pattern: '/api/x', network_response_status: 200 },
    ['Network: GET /api/x · resp 200'],
  ],
  [
    'template-linked navigation',
    { step_type: 'navigation', template_id: 't1', template_step_id: 'ts1', template_version: 2 },
    [],
  ],
];

describe('WorkflowStepsCard detail lines', () => {
  it.each(TYPE_LINE_CASES)('%s', (_name, extra, lines) => {
    renderCards([step(extra)]);
    expect(screen.getByText('Do the thing')).toBeInTheDocument();
    for (const line of lines) {
      expect(screen.getByText(line)).toBeInTheDocument();
    }
  });

  it('repeat shows the dataset', () => {
    renderCards([step({ step_type: 'repeat', instruction: 'Each user', repeat_columns: ['email'], repeat_rows: [['a'], ['b']] })]);
    expect(screen.getByText('2 rows · email')).toBeInTheDocument();
  });
});

describe('card-specific lines', () => {
  const assertion = step({
    step_type: 'assertion',
    assertion_variable: 'total',
    validation_type: 'number',
    validation_operator: 'greater_then',
    validation_value: '3',
  });

  it('WorkflowStepsCard keeps the instruction and leads with the variable', () => {
    renderCards([assertion]);
    expect(screen.getByText('Do the thing')).toBeInTheDocument();
    const variable = screen.getByText('Variable: total');
    expect(variable.nextElementSibling).toHaveTextContent('Assertion: Number is greater than 3');
  });

  it('WorkflowStepsCard omits the variable line without a known validation type', () => {
    renderCards([step({ step_type: 'assertion', assertion_variable: 'total' })]);
    expect(screen.queryByText('Variable: total')).not.toBeInTheDocument();
  });

  it('WorkflowStepsCard shows no type lines for a navigation step', () => {
    const { container } = render(
      <WorkflowStepsCard
        steps={[step({ step_type: 'navigation' })] as any}
        onReorder={vi.fn()}
        onUpdateStep={vi.fn()}
        onDeleteStep={vi.fn()}
        onAddStep={vi.fn()}
        usecaseId="u"
      />,
    );
    expect(container.querySelectorAll('.step-details')).toHaveLength(0);
  });
});
