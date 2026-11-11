/**
 * ExecutionSteps — table layout (`#` column, validation under the
 * instruction, small Trace / Act ID) and the `Row i/n` badge and row-group
 * header for steps unrolled from a repeat step. Fields are snake_case as
 * returned by the API. `{{name}}` tokens in the instruction and the
 * validation value render as `VAR` badges (resolver and badge have their own
 * tests; here: the wiring and one fixture covering every kind).
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import createWrapper from '@cloudscape-design/components/test-utils/dom';

import ExecutionSteps from '../ExecutionSteps';
import { api, type ExecutionVariablesResponse } from '../../../utils/api';
import type { ExecutionRef } from '../variableTokens';

vi.mock('../../../utils/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/api')>()),
  api: { post: vi.fn(), get: vi.fn() },
}));

afterEach(() => {
  cleanup();
  vi.mocked(api.post).mockReset();
});

const plain = (sort: number, instruction: string) => ({
  sk: `EXECUTION_STEP#${sort}`, sort, instruction, status: 'success', step_type: 'navigation',
});
const expanded = (sort: number, instruction: string, row: number, total: number) => ({
  ...plain(sort, instruction),
  repeat_step_id: 'r1', repeat_label: 'Login as each user',
  repeat_row_index: row, repeat_row_total: total,
  row_variables: { email: `u${row}@x.test`, RepeatIndex: String(row), RepeatTotal: String(total) },
});

const MIXED = [
  plain(1, 'Open the site'),
  expanded(2, 'Type u1@x.test', 1, 2),
  expanded(3, 'Check role', 1, 2),
  expanded(4, 'Type u2@x.test', 2, 2),
  expanded(5, 'Check role', 2, 2),
  plain(6, 'Log out'),
];

/** Opens every collapsed detail box; validation / capture details start collapsed unless the step failed. */
function showAllDetails() {
  for (const button of screen.queryAllByRole('button', { name: 'Show details' })) fireEvent.click(button);
}

function renderSteps(steps: any[], { openDetails = true }: { openDetails?: boolean } = {}) {
  render(<ExecutionSteps executionSteps={steps} usecaseId="u" executionId="e" />);
  if (openDetails) showAllDetails();
}

describe('ExecutionSteps — repeat rows', () => {
  it('renders plain steps exactly as before (no badge, no group header)', () => {
    renderSteps([plain(1, 'Open the site'), plain(2, 'Log out')]);
    expect(screen.queryByText(/^Row \d+\/\d+$/)).not.toBeInTheDocument();
    expect(screen.queryByTestId('repeat-row-group')).not.toBeInTheDocument();
    expect(screen.getByText('Open the site')).toBeInTheDocument();
  });

  it('shows a Row i/n badge on every expanded step', () => {
    renderSteps(MIXED);
    expect(screen.getAllByText('Row 1/2')).toHaveLength(2);
    expect(screen.getAllByText('Row 2/2')).toHaveLength(2);
  });

  it('shows the Row i/n badge in the Instruction cell, not in the # cell', () => {
    const { container } = render(<ExecutionSteps executionSteps={MIXED} usecaseId="u" executionId="e" />);
    const table = createWrapper(container).findTable()!;
    // Table row 3 = step 2, the first step of dataset row 1 (row 2 is its group row).
    expect(table.findBodyCell(3, 1)!.getElement().textContent).toBe('2');
    const instructionCell = table.findBodyCell(3, 3)!.getElement();
    expect(follows(within(instructionCell).getByText('Row 1/2'), within(instructionCell).getByTestId('step-instruction')))
      .toBe(true);
    expect(within(instructionCell).queryByTestId('repeat-row-group')).not.toBeInTheDocument();
  });

  it('adds a group row with a Repeat badge before the first step of each dataset row', () => {
    const { container } = render(<ExecutionSteps executionSteps={MIXED} usecaseId="u" executionId="e" />);
    const table = createWrapper(container).findTable()!;
    // 6 steps + 2 group rows.
    expect(table.findRows()).toHaveLength(8);
    for (const [row, label] of [[2, 'Login as each user — row 1 of 2'], [5, 'Login as each user — row 2 of 2']] as const) {
      const cell = table.findBodyCell(row, 3)!.getElement();
      const group = within(cell).getByTestId('repeat-group-row');
      expect(createWrapper(group).findBadge()!.getElement().textContent).toBe('Repeat');
      expect(within(group).getByTestId('repeat-row-group').textContent).toBe(label);
      // The group row is not a step: no number, no status, no instruction or trace.
      expect(table.findBodyCell(row, 1)!.getElement().textContent).toBe('');
      expect(table.findBodyCell(row, 2)!.getElement().textContent).toBe('');
      expect(within(cell).queryByTestId('step-instruction')).not.toBeInTheDocument();
    }
    // Steps keep their own rows and order around the group rows.
    expect([1, 3, 4, 6, 7, 8].map((row) => table.findBodyCell(row, 1)!.getElement().textContent))
      .toEqual(['1', '2', '3', '4', '5', '6']);
  });

  it('shows the repeat label once per row group, when the row changes', () => {
    renderSteps(MIXED);
    const headers = screen.getAllByTestId('repeat-row-group');
    expect(headers.map((h) => h.textContent)).toEqual([
      'Login as each user — row 1 of 2',
      'Login as each user — row 2 of 2',
    ]);
  });

  it('starts a new group when a different repeat follows directly', () => {
    const other = { ...expanded(3, 'Other', 1, 1), repeat_step_id: 'r2', repeat_label: 'Second loop' };
    renderSteps([expanded(1, 'A', 1, 1), expanded(2, 'B', 1, 1), other]);
    const headers = screen.getAllByTestId('repeat-row-group');
    expect(headers.map((h) => h.textContent)).toEqual([
      'Login as each user — row 1 of 1',
      'Second loop — row 1 of 1',
    ]);
  });
});

const validated = (sort: number, instruction: string, extra: Record<string, unknown> = {}) => ({
  ...plain(sort, instruction),
  step_type: 'validation',
  validation_type: 'text',
  validation_operator: 'contains',
  validation_value: 'Welcome',
  ...extra,
});

/** True when `later` comes after `earlier` in document order. */
function follows(earlier: Element, later: Element): boolean {
  return Boolean(earlier.compareDocumentPosition(later) & Node.DOCUMENT_POSITION_FOLLOWING);
}

describe('ExecutionSteps — step type', () => {
  const stepTypeOf = (container: HTMLElement, row: number) =>
    within(createWrapper(container).findTable()!.findBodyCell(row, 3)!.getElement()).queryByTestId('step-type');

  it('shows the shared step type badge at the top of every Instruction cell, before the instruction', () => {
    const steps = [
      plain(1, 'Open the site'),
      { ...plain(2, 'Return the order number'), step_type: 'retrieve_value', capture_variable: 'order_id' },
      { ...plain(3, 'Click Place order'), step_type: 'network_assertion' },
      { ...plain(4, 'Focus the password field'), step_type: 'secret' },
    ];
    const { container } = render(<ExecutionSteps executionSteps={steps} usecaseId="u" executionId="e" />);
    showAllDetails();
    expect([1, 2, 3, 4].map((row) => stepTypeOf(container, row)?.textContent)).toEqual([
      'Navigation', 'Value', 'Network', 'Secret',
    ]);
    const cell = createWrapper(container).findTable()!.findBodyCell(2, 3)!.getElement();
    expect(createWrapper(within(cell).getByTestId('step-type')).findBadge()!.getElement().className)
      .toMatch(/badge-color-blue(_|\b)/);
    expect(follows(within(cell).getByTestId('step-type'), within(cell).getByTestId('step-instruction'))).toBe(true);
    expect(follows(within(cell).getByTestId('step-type'), within(cell).getByTestId('step-capture'))).toBe(true);
  });

  it('shows Navigation for a step without step_type, like the step editor', () => {
    const { container } = render(
      <ExecutionSteps executionSteps={[{ ...plain(1, 'A'), step_type: undefined }]} usecaseId="u" executionId="e" />,
    );
    expect(stepTypeOf(container, 1)?.textContent).toBe('Navigation');
  });

  it('puts the Row i/n badge on the step type line', () => {
    const { container } = render(<ExecutionSteps executionSteps={MIXED} usecaseId="u" executionId="e" />);
    // Table row 3 = step 2 (row 2 is the group row of dataset row 1).
    const cell = createWrapper(container).findTable()!.findBodyCell(3, 3)!.getElement();
    const heading = within(cell).getByTestId('step-heading');
    expect(within(heading).getByTestId('step-type').textContent).toBe('Navigation');
    expect(within(heading).getByText('Row 1/2')).toBeInTheDocument();
    expect(follows(heading, within(cell).getByTestId('step-instruction'))).toBe(true);
  });
});

describe('ExecutionSteps — not yet run', () => {
  const instructionCell = (container: HTMLElement, row: number) =>
    createWrapper(container).findTable()!.findBodyCell(row, 3)!.getElement();

  it('greys out the Instruction cell of steps that have not run yet', () => {
    const steps = [
      { ...plain(1, 'Done'), status: 'success' },
      { ...plain(2, 'Broke'), status: 'failed' },
      { ...plain(3, 'Running'), status: 'executing' },
      { ...plain(4, 'From cache'), status: 'cached' },
      { ...plain(5, 'Waiting'), status: 'pending' },
      { ...plain(6, 'No status yet'), status: undefined },
    ];
    const { container } = render(<ExecutionSteps executionSteps={steps} usecaseId="u" executionId="e" />);
    const notRun = [1, 2, 3, 4, 5, 6].map((row) => Boolean(instructionCell(container, row).querySelector('.step-cell--not-run')));
    expect(notRun).toEqual([false, false, false, false, true, true]);
  });

  it('greys out a repeat group row whose first step has not run yet', () => {
    const steps = [
      { ...expanded(1, 'A', 1, 2), status: 'success' },
      { ...expanded(2, 'B', 2, 2), status: 'pending' },
    ];
    const { container } = render(<ExecutionSteps executionSteps={steps} usecaseId="u" executionId="e" />);
    // Rows: group 1, step 1, group 2, step 2.
    const notRun = [1, 2, 3, 4].map((row) => Boolean(instructionCell(container, row).querySelector('.step-cell--not-run')));
    expect(notRun).toEqual([false, false, true, true]);
  });
});

describe('ExecutionSteps — layout', () => {
  it('labels the step column # and has no Validation column', () => {
    const { container } = render(
      <ExecutionSteps executionSteps={[plain(1, 'Open the site')]} usecaseId="u" executionId="e" />,
    );
    const headers = createWrapper(container).findTable()!.findColumnHeaders().map((h) => h.getElement().textContent);
    expect(headers).toEqual(['#', 'Status', 'Instruction']);
  });

  it('renders the validation box below the instruction', () => {
    renderSteps([validated(1, 'Check the greeting', { act_id: 'act-1' })]);
    const box = screen.getByTestId('step-validation');
    expect(box).toHaveClass('step-detail');
    expect(follows(screen.getByText('Check the greeting'), box)).toBe(true);
  });

  it('shows the validation type and operator as small key/value pairs at the top of the box', () => {
    renderSteps([validated(1, 'Check the greeting')]);
    const meta = within(screen.getByTestId('step-validation')).getByTestId('step-validation-meta');
    expect(meta.textContent).toBe('TypetextOperatorcontains');
    for (const key of ['Type', 'Operator']) {
      expect(within(meta).getByText(key).className).toMatch(/color-text-body-secondary/);
      expect(within(meta).getByText(key).className).toMatch(/font-size-body-s/);
    }
    expect(within(meta).getByText('text').className).toMatch(/font-size-body-s/);
  });

  it('shows the expected value and, underneath, the actual value', () => {
    renderSteps([validated(1, 'Check the greeting', { actual_value: 'Welcome back' })]);
    const box = screen.getByTestId('step-validation');
    const expected = within(box).getByTestId('step-validation-expected');
    const actual = within(box).getByTestId('step-validation-actual');
    expect(expected.textContent).toBe('ExpectedWelcome');
    expect(actual.textContent).toBe('ActualWelcome back');
    expect(follows(within(box).getByTestId('step-validation-meta'), expected)).toBe(true);
    expect(follows(expected, actual)).toBe(true);
  });

  it('shows a dash as the actual value until the runner recorded one', () => {
    renderSteps([validated(1, 'Check the greeting')]);
    expect(screen.getByTestId('step-validation-actual').textContent).toBe('Actual—');
  });

  it('renders no validation box and no placeholder for steps without validation', () => {
    renderSteps([plain(1, 'Open the site')]);
    expect(screen.queryByTestId('step-validation')).not.toBeInTheDocument();
    expect(screen.queryByText('Expected')).not.toBeInTheDocument();
    expect(screen.queryByText('-')).not.toBeInTheDocument();
  });

  const retrieve = (sort: number, extra: Record<string, unknown> = {}) => ({
    ...plain(sort, 'Return the order number'),
    step_type: 'retrieve_value',
    capture_variable: 'order_id',
    value_type: 'number',
    ...extra,
  });

  it('renders the capture box below the instruction', () => {
    renderSteps([retrieve(1, { act_id: 'act-1', actual_value: '4711' })]);
    const box = screen.getByTestId('step-capture');
    expect(box).toHaveClass('step-detail');
    expect(follows(screen.getByText('Return the order number'), box)).toBe(true);
  });

  it('shows the captured variable name and value type as small key/value pairs, then the captured value', () => {
    renderSteps([retrieve(1, { actual_value: '4711' })]);
    const box = screen.getByTestId('step-capture');
    const meta = within(box).getByTestId('step-capture-meta');
    expect(meta.textContent).toBe('Variableorder_idTypenumber');
    expect(within(meta).getByText('Variable').className).toMatch(/color-text-body-secondary/);
    const value = within(box).getByTestId('step-capture-value');
    expect(value.textContent).toBe('Value4711');
    expect(follows(meta, value)).toBe(true);
  });

  it('shows the type string when the step has no value_type', () => {
    renderSteps([retrieve(1, { value_type: undefined, actual_value: 'abc' })]);
    expect(screen.getByTestId('step-capture-meta').textContent).toBe('Variableorder_idTypestring');
  });

  it('shows a dash as the captured value until the step has run', () => {
    renderSteps([retrieve(1, { status: 'pending' })]);
    expect(screen.getByTestId('step-capture-value').textContent).toBe('Value—');
  });

  it('shows the transform operation instead of a type for transform steps', () => {
    renderSteps([{
      ...plain(1, 'Lower-case the name'), step_type: 'transform', capture_variable: 'slug',
      transform_operation: 'lowercase', actual_value: 'ann',
    }]);
    expect(screen.getByTestId('step-capture-meta').textContent).toBe('VariableslugOperationlowercase');
    expect(screen.getByTestId('step-capture-value').textContent).toBe('Valueann');
  });

  it("shows the step's own captured value, not the run's final value of that variable", () => {
    render(
      <ExecutionSteps
        executionSteps={[retrieve(1, { actual_value: 'ORD-1' })]}
        usecaseId="u"
        executionId="e"
        variables={{ variables: [], execution_variables: {}, runtime_variables: [{ key: 'order_id', value: 'ORD-2' }] }}
      />,
    );
    showAllDetails();
    expect(screen.getByTestId('step-capture-value').textContent).toBe('ValueORD-1');
  });

  it('renders no capture box for steps without capture_variable', () => {
    renderSteps([plain(1, 'Open the site'), validated(2, 'Check the greeting')]);
    expect(screen.queryByTestId('step-capture')).not.toBeInTheDocument();
  });

  it('renders Trace and the Act ID in small text', () => {
    renderSteps([plain(1, 'Open the site')].map((s) => ({ ...s, act_id: 'act-123' })));
    expect(screen.getByRole('button', { name: 'Trace' }).className).toMatch(/font-size-body-s/);
    expect(screen.getByText('act-123').closest('[class*="font-size-body-s"]')).not.toBeNull();
    expect(screen.getByRole('button', { name: 'Copy Act ID' })).toBeInTheDocument();
  });

  it('opens the trace modal and requests the signed URL when Trace is clicked', async () => {
    vi.mocked(api.post).mockResolvedValue({ signedUrl: 'https://example.test/trace.html' });
    renderSteps([{ ...plain(3, 'Open the site'), act_id: 'act-9' }]);
    fireEvent.click(screen.getByRole('button', { name: 'Trace' }));
    expect(api.post).toHaveBeenCalledWith('generate-s3-url', {
      usecaseId: 'u', executionId: 'e', fileType: 'html', actId: 'act-9',
    });
    expect(await screen.findByText('Step 3: act-9')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTitle('Nova Act Trace Viewer')).toBeInTheDocument());
  });

  it('centers the step number and the status icon in their cells', () => {
    const { container } = render(
      <ExecutionSteps executionSteps={[plain(7, 'Open the site')]} usecaseId="u" executionId="e" />,
    );
    const table = createWrapper(container).findTable()!;
    for (const column of [1, 2]) {
      const cell = table.findBodyCell(1, column)!.getElement();
      // Cloudscape Box textAlign="center" → class awsui_t-center_<hash>.
      expect(cell.querySelector('[class*="t-center"]')).not.toBeNull();
    }
    expect(table.findBodyCell(1, 1)!.getElement().textContent).toBe('7');
  });

  it('renders the status as an icon only, labelled with the status for screen readers and on hover', () => {
    const { container } = render(
      <ExecutionSteps
        executionSteps={[plain(1, 'Open the site'), { ...plain(2, 'Log out'), status: 'failed' }]}
        usecaseId="u"
        executionId="e"
      />,
    );
    const table = createWrapper(container).findTable()!;
    for (const [row, status] of [[1, 'success'], [2, 'failed']] as const) {
      const cell = table.findBodyCell(row, 2)!.getElement();
      expect(cell.textContent).toBe('');
      expect(within(cell).getByRole('img', { name: status })).toBeInTheDocument();
      expect(cell.querySelector(`[title="${status}"]`)).not.toBeNull();
    }
  });

  it('shows "Executed from cache" and no Trace for cached steps', () => {
    renderSteps([{ ...plain(1, 'Open the site'), act_id: 'cached' }]);
    expect(within(screen.getByTestId('step-actions')).getByText('Executed from cache')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Trace' })).not.toBeInTheDocument();
  });

  it('puts Trace and the Act ID at the top of the Instruction cell, on the right of the step type line', () => {
    renderSteps([validated(1, 'Check the greeting', { act_id: 'act-1', logs: 'boom' })]);
    const heading = screen.getByTestId('step-heading');
    const actions = within(heading).getByTestId('step-actions');
    expect(actions).toHaveClass('step-heading__actions');
    expect(within(actions).getByRole('button', { name: 'Trace' })).toBeInTheDocument();
    expect(within(actions).getByText('act-1')).toBeInTheDocument();
    expect(follows(within(heading).getByTestId('step-type'), actions)).toBe(true);
    expect(follows(heading, screen.getByTestId('step-instruction'))).toBe(true);
    expect(follows(screen.getByTestId('step-validation'), screen.getByText('boom'))).toBe(true);
  });

  it('renders no action area for steps without trace and not from cache', () => {
    renderSteps([{ ...plain(1, 'Open the site'), act_id: undefined }]);
    expect(screen.queryByTestId('step-actions')).not.toBeInTheDocument();
  });

  it('keeps the Row 10/10 badge on one line (non-breaking space)', () => {
    renderSteps([expanded(1, 'A', 10, 10)]);
    const badge = screen.getByText('Row 10/10');
    expect(badge.textContent).toBe('Row\u00a010/10');
  });
});

const EXECUTION: ExecutionRef = { sk: 'EXECUTION#exec-42', execution_id: 'exec-42', created_at: '2025-01-02T03:04:05Z' };
const VARIABLES: ExecutionVariablesResponse = {
  variables: [{ key: 'product', value: 'stale use-case value' }],
  runtime_variables: [{ key: 'order_id', value: 'ORD-7' }],
  execution_variables: { product: 'MacBook Pro', BaseUrl: 'https://Shop.example' },
};

const capture = (sort: number, name: string) => ({
  ...plain(sort, `Read ${name}`), step_type: 'retrieve_value', capture_variable: name,
});

const ALL_KINDS = [
  plain(1, 'Search for {{product}} now'),
  capture(2, 'order_id'),
  capture(3, 'tracking_code'),
  plain(4, 'Open order {{order_id}} and {{tracking_code}}'),
  plain(5, 'Login as user_{{UniqueID}} at {{Time}} in {{ExecutionID}}'),
  plain(6, 'Type {{prodcut}} and {{ product }}'),
  validated(7, 'Check the total', { validation_value: 'Total for {{product}}!' }),
  { ...expanded(8, 'Type {{email}} (row {{RepeatIndex}})', 1, 2), sk: 'EXECUTION_STEP#8' },
  { ...expanded(9, 'Type {{email}} (row {{RepeatIndex}})', 2, 2), sk: 'EXECUTION_STEP#9' },
  plain(10, 'Open the site'),
];

type BadgeInfo = { kind: string | null; value: string | null | undefined; color: string };

/** `dark-blue` for the custom variable badge class, otherwise the Cloudscape badge colour. */
function badgeColor(badge: Element): string {
  if (badge.classList.contains('variable-badge')) return 'dark-blue';
  return /badge-color-([a-z-]+?)_/.exec(badge.className)?.[1] ?? '';
}

function badgesIn(element: Element): BadgeInfo[] {
  return Array.from(element.querySelectorAll('[data-testid="variable-badge"]')).map((badge) => ({
    kind: badge.getAttribute('data-kind'),
    value: badge.querySelector('[title]')?.getAttribute('title'),
    color: badgeColor(badge),
  }));
}

function instructionOf(sort: number): Element {
  const element = screen.getAllByTestId('step-instruction').find((el) => el.getAttribute('data-sort') === String(sort));
  if (!element) throw new Error(`no instruction for step ${sort}`);
  return element;
}

function renderWithVariables(
  steps: any[],
  variables: ExecutionVariablesResponse | null = VARIABLES,
  execution: ExecutionRef | null = EXECUTION,
) {
  const result = render(
    <ExecutionSteps executionSteps={steps} usecaseId="u" executionId="exec-42" variables={variables} execution={execution} />,
  );
  showAllDetails();
  return result;
}

describe('ExecutionSteps — details toggle', () => {
  const toggleIn = (container: ParentNode = document.body) =>
    within(container as HTMLElement).queryByRole('button', { name: /^(Show|Hide) details$/ });

  it('collapses the details of a step that did not fail and offers Show details on the right of the heading', () => {
    renderSteps([validated(1, 'Check the greeting', { act_id: 'act-1' })], { openDetails: false });
    expect(screen.queryByTestId('step-validation')).not.toBeInTheDocument();
    const actions = screen.getByTestId('step-actions');
    const toggle = within(actions).getByRole('button', { name: 'Show details' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    // Rightmost control of the heading, after Trace / Act ID.
    expect(follows(within(actions).getByRole('button', { name: 'Trace' }), toggle)).toBe(true);
  });

  it('opens and closes the details with the toggle', () => {
    renderSteps([validated(1, 'Check the greeting')], { openDetails: false });
    fireEvent.click(screen.getByRole('button', { name: 'Show details' }));
    expect(screen.getByTestId('step-validation')).toBeInTheDocument();
    const hide = screen.getByRole('button', { name: 'Hide details' });
    expect(hide).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(hide);
    expect(screen.queryByTestId('step-validation')).not.toBeInTheDocument();
  });

  it.each(['failed', 'error'])('shows the details of a %s step by default, with Hide details', (status) => {
    renderSteps([validated(1, 'Check the greeting', { status, actual_value: 'Bye' })], { openDetails: false });
    expect(screen.getByTestId('step-validation-actual').textContent).toBe('ActualBye');
    expect(screen.getByRole('button', { name: 'Hide details' })).toBeInTheDocument();
  });

  it('collapses capture details of a successful step as well', () => {
    renderSteps([{ ...plain(1, 'Return the order number'), step_type: 'retrieve_value', capture_variable: 'id' }], {
      openDetails: false,
    });
    expect(screen.queryByTestId('step-capture')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Show details' }));
    expect(screen.getByTestId('step-capture')).toBeInTheDocument();
  });

  it('offers no toggle for steps without details', () => {
    renderSteps([plain(1, 'Open the site')], { openDetails: false });
    expect(toggleIn()).toBeNull();
  });

  it('keeps error logs visible while the details are collapsed', () => {
    renderSteps([validated(1, 'Check the greeting', { logs: 'Timed out' })], { openDetails: false });
    expect(screen.getByText('Timed out')).toBeInTheDocument();
  });

  it('opens the details when a polled step turns failed, unless the user toggled it', () => {
    const withStatus = (status: string) => [
      validated(1, 'First check', { status }),
      validated(2, 'Second check', { status }),
    ];
    const { rerender } = render(<ExecutionSteps executionSteps={withStatus('executing')} usecaseId="u" executionId="e" />);
    // The user opens and closes step 1 again: that choice sticks for step 1.
    fireEvent.click(screen.getAllByRole('button', { name: 'Show details' })[0]);
    fireEvent.click(screen.getByRole('button', { name: 'Hide details' }));
    rerender(<ExecutionSteps executionSteps={withStatus('failed')} usecaseId="u" executionId="e" />);
    const boxes = screen.getAllByTestId('step-validation');
    expect(boxes).toHaveLength(1);
    expect(follows(screen.getByText('Second check'), boxes[0])).toBe(true);
  });
});

describe('ExecutionSteps — variable badges', () => {
  it('renders a regular variable from execution_variables as a dark blue badge in original casing', () => {
    renderWithVariables(ALL_KINDS);
    expect(badgesIn(instructionOf(1))).toEqual([{ kind: 'regular', value: 'MacBook Pro', color: 'dark-blue' }]);
  });

  it('preserves the text before and after a token', () => {
    renderWithVariables(ALL_KINDS);
    const instruction = instructionOf(1);
    const texts = Array.from(instruction.childNodes).map((node) => (
      (node as Element).getAttribute?.('data-testid') === 'variable-badge' ? '[badge]' : node.textContent
    ));
    expect(texts).toEqual(['Search for ', '[badge]', ' now']);
  });

  it('renders a captured runtime variable with its value and a pending one as a placeholder', () => {
    renderWithVariables(ALL_KINDS);
    const instruction = instructionOf(4);
    expect(badgesIn(instruction)).toEqual([
      { kind: 'runtime', value: 'ORD-7', color: 'dark-blue' },
      { kind: 'runtime', value: 'tracking_code', color: 'dark-blue' },
    ]);
    const values = instruction.querySelectorAll('[data-testid="variable-badge"] [title]');
    expect(values[0].className).not.toMatch(/placeholder/);
    expect(values[1].className).toMatch(/placeholder/);
  });

  it('renders UniqueID, Time and ExecutionID as grey predefined badges with uppercase placeholder labels', () => {
    renderWithVariables(ALL_KINDS);
    expect(badgesIn(instructionOf(5))).toEqual([
      { kind: 'predefined', value: 'UNIQUE_ID', color: 'dark-blue' },
      { kind: 'predefined', value: 'TIMESTAMP', color: 'dark-blue' },
      { kind: 'predefined', value: 'EXECUTION_ID', color: 'dark-blue' },
    ]);
    const values = instructionOf(5).querySelectorAll('[data-testid="variable-badge"] [title]');
    expect(Array.from(values).every((value) => /placeholder/.test(value.className))).toBe(true);
    expect(instructionOf(5).textContent).toMatch(/^Login as user_VAR/);
  });

  it('resolves dataset columns per repeat row and shows RepeatIndex as a placeholder label', () => {
    renderWithVariables(ALL_KINDS);
    expect(badgesIn(instructionOf(8))).toEqual([
      { kind: 'regular', value: 'u1@x.test', color: 'dark-blue' },
      { kind: 'predefined', value: 'REPEAT_INDEX', color: 'dark-blue' },
    ]);
    expect(badgesIn(instructionOf(9))).toEqual([
      { kind: 'regular', value: 'u2@x.test', color: 'dark-blue' },
      { kind: 'predefined', value: 'REPEAT_INDEX', color: 'dark-blue' },
    ]);
  });

  it('renders an unknown name and a token with whitespace as UNDEFINED_VALUE badges', () => {
    renderWithVariables(ALL_KINDS);
    expect(badgesIn(instructionOf(6))).toEqual([
      { kind: 'undefined', value: 'UNDEFINED_VALUE', color: 'dark-blue' },
      { kind: 'undefined', value: 'UNDEFINED_VALUE', color: 'dark-blue' },
    ]);
  });

  it('renders the badge in the expected value of the validation box', () => {
    renderWithVariables(ALL_KINDS);
    const expected = screen.getByTestId('step-validation-expected');
    expect(badgesIn(expected)).toEqual([{ kind: 'regular', value: 'MacBook Pro', color: 'dark-blue' }]);
    expect(expected.textContent).toBe('ExpectedTotal for VARMacBook Pro!');
  });

  it('renders text without tokens exactly as before, without badges', () => {
    renderWithVariables(ALL_KINDS);
    const instruction = instructionOf(10);
    expect(instruction.textContent).toBe('Open the site');
    expect(badgesIn(instruction)).toEqual([]);
    expect(screen.getByText('Open the site')).toBeInTheDocument();
  });

  it('renders badges without crashing and without fetching before variables and execution are loaded', () => {
    renderWithVariables(ALL_KINDS, null, null);
    expect(badgesIn(instructionOf(1))).toEqual([{ kind: 'undefined', value: 'UNDEFINED_VALUE', color: 'dark-blue' }]);
    expect(badgesIn(instructionOf(4))).toEqual([
      { kind: 'runtime', value: 'order_id', color: 'dark-blue' },
      { kind: 'runtime', value: 'tracking_code', color: 'dark-blue' },
    ]);
    expect(badgesIn(instructionOf(5))[2]).toEqual({ kind: 'predefined', value: 'EXECUTION_ID', color: 'dark-blue' });
    expect(api.get).not.toHaveBeenCalled();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('updates a pending runtime badge when the polled variables carry the captured value', () => {
    const { rerender } = renderWithVariables(ALL_KINDS);
    const captured: ExecutionVariablesResponse = {
      ...VARIABLES,
      runtime_variables: [...VARIABLES.runtime_variables, { key: 'tracking_code', value: 'TRK-1' }],
    };
    rerender(
      <ExecutionSteps executionSteps={ALL_KINDS} usecaseId="u" executionId="exec-42" variables={captured} execution={EXECUTION} />,
    );
    expect(badgesIn(instructionOf(4))[1]).toEqual({ kind: 'runtime', value: 'TRK-1', color: 'dark-blue' });
  });

  it('leaves the repeat row-group header raw', () => {
    renderWithVariables([{ ...expanded(1, '{{email}}', 1, 1), repeat_label: 'Each {{email}}', act_id: 'act-1' }]);
    expect(screen.getByTestId('repeat-row-group').textContent).toBe('Each {{email}} — row 1 of 1');
  });
});
