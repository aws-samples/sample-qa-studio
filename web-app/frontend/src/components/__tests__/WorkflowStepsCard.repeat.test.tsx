/**
 * WorkflowStepsCard — repeat blocks: nested children, "Add step inside",
 * delete confirmation mentioning the children, block-aware drop handling.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import WorkflowStepsCard from '../WorkflowStepsCard';

const modalProps = vi.fn();
vi.mock('../usecase/StepFormModal', () => ({
  default: function MockStepFormModal(props: any) {
    modalProps(props);
    if (!props.visible) return null;
    return (
      <div data-testid="step-form-modal">
        <span>{props.title}</span>
        <span data-testid="modal-parent">{props.parentStepId ?? ''}</span>
        <button onClick={() => props.onSubmit({ step_type: 'navigation', instruction: 'new', parent_step_id: props.parentStepId })}>
          submit-mock
        </button>
      </div>
    );
  },
}));

afterEach(() => cleanup());

const step = (sk: string, sort: number, extra: Record<string, unknown> = {}) => ({
  pk: 'USECASE#u', sk: `STEP#${sk}`, id: sk, usecaseId: 'u', sort, instruction: `Instruction ${sk}`,
  step_type: 'navigation', ...extra,
});

const STEPS = [
  step('a', 1),
  step('R1', 2, { step_type: 'repeat', instruction: 'Login as each user', repeat_columns: ['email', 'role'], repeat_rows: [['x', 'y'], ['z', 'w'], ['q', 'r']] }),
  step('c1', 3, { parent_step_id: 'R1' }),
  step('c2', 4, { parent_step_id: 'R1' }),
  step('b', 5),
];

function renderCard(steps = STEPS) {
  const onReorder = vi.fn().mockResolvedValue(undefined);
  const onUpdateStep = vi.fn().mockResolvedValue(undefined);
  const onDeleteStep = vi.fn().mockResolvedValue(undefined);
  const onAddStep = vi.fn().mockResolvedValue(undefined);
  render(
    <WorkflowStepsCard
      steps={steps}
      onReorder={onReorder}
      onUpdateStep={onUpdateStep}
      onDeleteStep={onDeleteStep}
      onAddStep={onAddStep}
      usecaseId="u"
    />,
  );
  return { onReorder, onUpdateStep, onDeleteStep, onAddStep };
}

describe('WorkflowStepsCard — nesting', () => {
  it('renders children indented under their repeat with the dataset summary', () => {
    renderCard();
    const nested = screen.getByTestId('repeat-children');
    const childCards = within(nested).getAllByTestId('child-step-card');
    expect(childCards.map((c) => c.textContent)).toEqual([
      expect.stringContaining('Instruction c1'),
      expect.stringContaining('Instruction c2'),
    ]);
    expect(screen.getByText('3 rows · email, role')).toBeInTheDocument();
    expect(screen.getByText('Repeat')).toBeInTheDocument();
    // Top-level cards: a, R1, b
    expect(screen.getAllByTestId('step-card')).toHaveLength(3);
  });

  const emptyRepeat = step('R', 1, { step_type: 'repeat', instruction: 'Empty', repeat_columns: ['a'], repeat_rows: [['1']] });

  it('shows the empty hint once, inside the block of a repeat without children', () => {
    renderCard([emptyRepeat]);
    expect(screen.getAllByText(/No steps inside yet/)).toHaveLength(1);
    expect(within(screen.getByTestId('repeat-children')).getByText(/No steps inside yet/)).toBeInTheDocument();
  });

  it('drops the empty hint once the repeat has a child', () => {
    renderCard([emptyRepeat, step('c', 2, { parent_step_id: 'R' })]);
    expect(screen.queryByText(/No steps inside yet/)).not.toBeInTheDocument();
  });

  it('keeps the empty hint when the only nested-looking step is an orphan of another parent', () => {
    renderCard([emptyRepeat, step('o', 2, { parent_step_id: 'ghost' })]);
    expect(screen.getAllByText(/No steps inside yet/)).toHaveLength(1);
  });

  it('renders an orphan child flat with a warning', () => {
    renderCard([step('a', 1), step('o', 2, { parent_step_id: 'ghost' })]);
    expect(screen.getAllByTestId('step-card')).toHaveLength(2);
    expect(screen.getByText(/Parent repeat step not found/)).toBeInTheDocument();
  });
});

describe('WorkflowStepsCard — application dataset repeat', () => {
  const DATASETS = [{ dataset_id: 'ds-1', name: 'customers', description: '', column_count: 3, row_count: 5, updated_at: '' }];
  const datasetRepeat = step('R2', 1, { step_type: 'repeat', instruction: 'Each customer', dataset_id: 'ds-1' });

  function renderWithDatasets(steps = [datasetRepeat]) {
    modalProps.mockClear();
    render(
      <WorkflowStepsCard
        steps={steps}
        onReorder={vi.fn()}
        onUpdateStep={vi.fn()}
        onDeleteStep={vi.fn()}
        onAddStep={vi.fn()}
        usecaseId="u"
        applicationId="app-1"
        datasets={DATASETS}
      />,
    );
  }

  it('shows the dataset name instead of row counts and raises no "Dataset is empty" issue', () => {
    renderWithDatasets();
    expect(screen.getByText('Application dataset: customers · 5 rows · 3 columns')).toBeInTheDocument();
    expect(screen.queryByText(/Dataset is empty/)).not.toBeInTheDocument();
    expect(screen.queryByText(/0 rows/)).not.toBeInTheDocument();
  });

  it('still flags a repeat with neither dataset_id nor inline rows', () => {
    renderWithDatasets([step('R3', 1, { step_type: 'repeat', instruction: 'Broken' })]);
    expect(screen.getByText(/Dataset is empty/)).toBeInTheDocument();
  });

  it('passes applicationId and datasets to the step modal', () => {
    renderWithDatasets();
    expect(modalProps).toHaveBeenCalledWith(expect.objectContaining({ applicationId: 'app-1', datasets: DATASETS }));
  });
});

describe('WorkflowStepsCard — Add step inside', () => {
  it('opens the modal with parentStepId and inserts at the end of the block', async () => {
    const user = userEvent.setup();
    const { onAddStep } = renderCard();
    const addInside = screen.getByRole('button', { name: 'Add step inside' });
    await user.click(addInside);
    expect(screen.getByTestId('modal-parent')).toHaveTextContent('R1');
    expect(screen.getByText('Add Step Inside Repeat')).toBeInTheDocument();
    await user.click(screen.getByText('submit-mock'));
    expect(onAddStep).toHaveBeenCalledWith(
      { step_type: 'navigation', instruction: 'new', parent_step_id: 'R1' },
      5, // after c2 (sort 4)
    );
  });

  it('"Add step below" a repeat lands after the whole block as a top-level step', async () => {
    const user = userEvent.setup();
    const { onAddStep } = renderCard();
    const repeatCard = screen.getAllByTestId('step-card')[1];
    await user.click(within(repeatCard).getByRole('button', { name: 'Add step below' }));
    expect(screen.getByTestId('modal-parent')).toHaveTextContent('');
    await user.click(screen.getByText('submit-mock'));
    expect(onAddStep.mock.calls[0][1]).toBe(5);
  });

  it('"Add step above" a child stays inside the repeat', async () => {
    const user = userEvent.setup();
    renderCard();
    const childCard = screen.getAllByTestId('child-step-card')[1];
    await user.click(within(childCard).getByRole('button', { name: 'Add step above' }));
    expect(screen.getByTestId('modal-parent')).toHaveTextContent('R1');
  });
});

describe('WorkflowStepsCard — delete', () => {
  it('confirmation for a repeat mentions the number of children', async () => {
    const user = userEvent.setup();
    const { onDeleteStep } = renderCard();
    const repeatCard = screen.getAllByTestId('step-card')[1];
    await user.click(within(repeatCard).getByRole('button', { name: 'Delete step' }));
    expect(screen.getByText(/contains/)).toHaveTextContent('2 steps');
    await user.click(screen.getByRole('button', { name: 'Delete' }));
    expect(onDeleteStep).toHaveBeenCalledWith('STEP#R1');
  });

  it('confirmation for a plain step has no children note', async () => {
    const user = userEvent.setup();
    renderCard();
    const plainCard = screen.getAllByTestId('step-card')[0];
    await user.click(within(plainCard).getByRole('button', { name: 'Delete step' }));
    expect(screen.queryByText(/contains/)).not.toBeInTheDocument();
  });
});
