import { ReactNode, useMemo, useState } from 'react';
import Header from '@cloudscape-design/components/header';
import Table from '@cloudscape-design/components/table';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import Link from '@cloudscape-design/components/link';
import Button from '@cloudscape-design/components/button';
import Modal from '@cloudscape-design/components/modal';
import Box from '@cloudscape-design/components/box';
import Badge from '@cloudscape-design/components/badge';
import SpaceBetween from '@cloudscape-design/components/space-between';
import CopyToClipboard from '@cloudscape-design/components/copy-to-clipboard';
import { api, ExecutionVariablesResponse } from '../../utils/api';
import { buildVariableContext, resolveTemplate, type ExecutionRef } from './variableTokens';
import { TemplateText } from './VariableBadge';
import StepTypeBadge from '../common/StepTypeBadge';
import './ExecutionSteps.css';

interface ExecutionStepsProps {
  executionSteps: any[];
  usecaseId: string;
  executionId: string;
  /** The panel's polled `/variables` response; `null` until loaded. */
  variables?: ExecutionVariablesResponse | null;
  /** The execution record (for `{{ExecutionID}}` / `{{CreatedAt}}`). */
  execution?: ExecutionRef | null;
}

function getStatusType(status: string) {
  switch (status) {
    case 'success': return 'success';
    case 'error':
    case 'failed': return 'error';
    case 'running':
    case 'executing': return 'in-progress';
    case 'pending': return 'pending';
    case 'cached': return 'success';
    default: return 'pending';
  }
}

/**
 * First line of a step's Instruction cell: the step type badge and, for steps
 * unrolled from a repeat, the `Row i/n` badge on the left; Trace / Act ID (or
 * "Executed from cache") on the right.
 */
function StepHeading({ step, actions }: { step: any; actions: ReactNode }) {
  return (
    <div className="step-heading" data-testid="step-heading">
      <span data-testid="step-type"><StepTypeBadge stepType={step.step_type} /></span>
      {step.repeat_row_index != null && (
        // Non-breaking space: the badge never wraps in a narrow panel.
        <Badge color="blue">{`Row\u00a0${step.repeat_row_index}/${step.repeat_row_total}`}</Badge>
      )}
      {actions && <div className="step-heading__actions" data-testid="step-actions">{actions}</div>}
    </div>
  );
}

/** A table row of its own before the first step of each dataset row of a repeat. */
interface RepeatGroupRow {
  rowType: 'repeat-group';
  label: string;
  rowIndex: number;
  rowTotal: number;
  /** The dataset row's first step has not run yet, so the group row is greyed out too. */
  notRun: boolean;
}

/** A step the runner has not reached yet: `pending`, or no status recorded at all. */
const hasNotRun = (step: any): boolean => !step.status || step.status === 'pending';

/** Instruction cell content; greyed out (`step-cell--not-run`) until the step has run. */
function StepCell({ notRun, children }: { notRun: boolean; children: ReactNode }) {
  return <div className={notRun ? 'step-cell step-cell--not-run' : 'step-cell'}>{children}</div>;
}

const isRepeatGroupRow = (item: any): item is RepeatGroupRow => item?.rowType === 'repeat-group';

/**
 * The steps with a group row inserted wherever a new dataset row of a repeat
 * starts (a different `repeat_step_id` or `repeat_row_index` than the step
 * before). Fields are snake_case as returned by the API.
 */
function withRepeatGroupRows(steps: any[]): (any | RepeatGroupRow)[] {
  const rows: (any | RepeatGroupRow)[] = [];
  steps.forEach((step, index) => {
    const previous = index > 0 ? steps[index - 1] : undefined;
    const startsGroup = step.repeat_row_index != null && (
      !previous
      || previous.repeat_step_id !== step.repeat_step_id
      || previous.repeat_row_index !== step.repeat_row_index
    );
    if (startsGroup) {
      rows.push({
        rowType: 'repeat-group',
        label: step.repeat_label || 'Repeat',
        rowIndex: step.repeat_row_index,
        rowTotal: step.repeat_row_total,
        notRun: hasNotRun(step),
      });
    }
    rows.push(step);
  });
  return rows;
}

function RepeatGroupLabel({ row }: { row: RepeatGroupRow }) {
  return (
    <div className="step-heading" data-testid="repeat-group-row">
      <StepTypeBadge stepType="repeat" />
      <Box variant="span" fontWeight="bold" data-testid="repeat-row-group">
        {`${row.label} — row ${row.rowIndex} of ${row.rowTotal}`}
      </Box>
    </div>
  );
}

/** Shown in a detail box for a value the runner has not recorded yet. */
const NOT_RECORDED = '—';

/** Step statuses whose details (validation / capture boxes) start open. */
const FAILED_STATUSES = new Set(['failed', 'error']);

/** Stable per-step key across polls (`EXECUTION_STEP#{uuid7}`). */
const stepKey = (step: any): string => step.sk ?? String(step.sort);

/** A step has details when it renders a validation or a capture box. */
const hasDetails = (step: any): boolean => Boolean(step.validation_type || step.capture_variable);

/** Grey box under a step's instruction (validation, capture). */
function DetailBox({ testId, children }: { testId: string; children: ReactNode }) {
  return <div className="step-detail" data-testid={testId}>{children}</div>;
}

/** Small key/value pairs at the top of a detail box, e.g. `Type string  Operator contains`. */
function DetailMeta({ testId, pairs }: { testId: string; pairs: [string, ReactNode][] }) {
  return (
    <div className="step-detail__meta" data-testid={testId}>
      {pairs.map(([label, value]) => (
        <span key={label} className="step-detail__pair">
          <Box variant="span" fontSize="body-s" color="text-body-secondary">{label}</Box>
          <Box variant="span" fontSize="body-s">{value}</Box>
        </span>
      ))}
    </div>
  );
}

/** One labelled value line of a detail box; labels share one column. */
function DetailRow({ testId, label, children }: { testId: string; label: string; children: ReactNode }) {
  return (
    <div className="step-detail__row" data-testid={testId}>
      <Box variant="span" color="text-body-secondary">{label}</Box>
      <span>{children}</span>
    </div>
  );
}

/**
 * Validation steps: type and operator, then the expected value and the
 * actual value (a dash until the runner recorded one).
 */
function ValidationBox({ step, expected }: { step: any; expected: ReactNode }) {
  if (!step.validation_type) return null;
  return (
    <DetailBox testId="step-validation">
      <DetailMeta
        testId="step-validation-meta"
        pairs={[['Type', step.validation_type], ['Operator', step.validation_operator]]}
      />
      <DetailRow testId="step-validation-expected" label="Expected">{expected}</DetailRow>
      <DetailRow testId="step-validation-actual" label="Actual">{step.actual_value || NOT_RECORDED}</DetailRow>
    </DetailBox>
  );
}

/**
 * Steps that capture a runtime variable (`retrieve_value`, `transform`): the
 * variable name and the value type (transform: the operation), then the value
 * this step captured. The runner records it as the step's `actual_value`, so
 * it is this step's value even when a later step overwrites the variable.
 */
function CaptureBox({ step }: { step: any }) {
  if (!step.capture_variable) return null;
  const kind: [string, ReactNode] = step.step_type === 'transform'
    ? ['Operation', step.transform_operation]
    : ['Type', step.value_type || 'string'];
  return (
    <DetailBox testId="step-capture">
      <DetailMeta testId="step-capture-meta" pairs={[['Variable', step.capture_variable], kind]} />
      <DetailRow testId="step-capture-value" label="Value">{step.actual_value || NOT_RECORDED}</DetailRow>
    </DetailBox>
  );
}

export default function ExecutionSteps({
  executionSteps,
  usecaseId,
  executionId,
  variables,
  execution,
}: ExecutionStepsProps) {
  const [traceModalVisible, setTraceModalVisible] = useState(false);
  const [traceUrl, setTraceUrl] = useState<string | null>(null);
  const [traceLoading, setTraceLoading] = useState(false);
  const [traceError, setTraceError] = useState<string | null>(null);
  const [traceTitle, setTraceTitle] = useState('');

  const handleTraceClick = async (step: any) => {
    const actId = step.actId || step.act_id;
    if (!actId || actId === 'cached' || actId === 'error') return;

    setTraceLoading(true);
    setTraceError(null);
    setTraceTitle(`Step ${step.sort}: ${actId}`);
    setTraceModalVisible(true);

    try {
      const result = await api.post('generate-s3-url', {
        usecaseId,
        executionId,
        fileType: 'html',
        actId,
      });
      if (result.signedUrl) {
        setTraceUrl(result.signedUrl);
      } else {
        setTraceError('No trace file found');
      }
    } catch (err: any) {
      setTraceError(err?.message || 'Failed to load trace');
    } finally {
      setTraceLoading(false);
    }
  };

  const handleCloseModal = () => {
    setTraceModalVisible(false);
    setTraceUrl(null);
    setTraceError(null);
  };

  // Validation / capture details start open only for failed steps. A user's
  // toggle wins over that default and survives the 10 s polls (keyed by sk).
  const [detailsToggled, setDetailsToggled] = useState<Record<string, boolean>>({});
  const detailsOpen = (step: any) => detailsToggled[stepKey(step)] ?? FAILED_STATUSES.has(step.status);
  const toggleDetails = (step: any) => {
    const open = detailsOpen(step);
    setDetailsToggled((previous) => ({ ...previous, [stepKey(step)]: !open }));
  };

  // `{{ExecutionID}}` resolves from the executionId prop: it is set before the
  // execution record loads and is the id the panel fetched the record with.
  const variableContext = useMemo(
    () => buildVariableContext({ ...execution, execution_id: executionId }, variables, executionSteps),
    [execution, executionId, variables, executionSteps],
  );
  const renderTemplate = (text: unknown, step: any) => (
    typeof text === 'string'
      ? <TemplateText segments={resolveTemplate(text, variableContext, step.row_variables)} />
      : text as ReactNode
  );

  // Steps unrolled from a repeat get a group row before each dataset row so
  // long expanded lists stay scannable.
  const tableItems = useMemo(() => withRepeatGroupRows(executionSteps), [executionSteps]);

  return (
    <>
      <Table
        header={<Header variant="h2">Execution Steps</Header>}
        columnDefinitions={[
          {
            id: 'sort',
            header: '#',
            // Holds only the step number; the `Row i/n` badge sits in the Instruction cell.
            width: 64,
            cell: (item: any) => (isRepeatGroupRow(item) ? null : <Box textAlign="center">{item.sort}</Box>),
          },
          {
            id: 'status',
            header: 'Status',
            // Icon only; the status text is the icon's aria label and hover title.
            width: 72,
            cell: (item: any) => (isRepeatGroupRow(item) ? null : (
              <Box textAlign="center">
                <span title={item.status}>
                  <StatusIndicator type={getStatusType(item.status)} iconAriaLabel={item.status} />
                </span>
              </Box>
            )),
          },
          {
            id: 'instruction',
            header: 'Instruction',
            cell: (item: any) => {
              if (isRepeatGroupRow(item)) {
                return <StepCell notRun={item.notRun}><RepeatGroupLabel row={item} /></StepCell>;
              }
              const actId = item.actId || item.act_id;
              const hasTrace = actId && actId !== 'cached' && actId !== 'error';
              const actions = hasTrace ? (
                // Inline CopyToClipboard renders the Act ID in a span
                // without its own font size, so it inherits body-s here.
                <Box fontSize="body-s">
                  <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                    <Link
                      variant="secondary"
                      fontSize="body-s"
                      onFollow={(event) => {
                        event.preventDefault();
                        handleTraceClick(item);
                      }}
                    >
                      Trace
                    </Link>
                    <CopyToClipboard
                      copyButtonAriaLabel="Copy Act ID"
                      copyErrorText="failed to copy"
                      copySuccessText="copied"
                      textToCopy={actId}
                      variant="inline"
                    />
                  </SpaceBetween>
                </Box>
              ) : actId === 'cached' ? (
                <Box fontSize="body-s" color="text-body-secondary">Executed from cache</Box>
              ) : null;
              const showToggle = hasDetails(item);
              const open = showToggle && detailsOpen(item);
              const controls = (actions || showToggle) ? (
                <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                  {actions}
                  {showToggle && (
                    <Button
                      variant="inline-icon"
                      iconName={open ? 'angle-up' : 'angle-down'}
                      ariaLabel={open ? 'Hide details' : 'Show details'}
                      ariaExpanded={open}
                      onClick={() => toggleDetails(item)}
                    />
                  )}
                </SpaceBetween>
              ) : null;
              return (
                <StepCell notRun={hasNotRun(item)}>
                  <SpaceBetween direction="vertical" size="xxs">
                    <StepHeading step={item} actions={controls} />
                    <span data-testid="step-instruction" data-sort={item.sort}>
                      {renderTemplate(item.instruction, item)}
                    </span>
                    {open && <ValidationBox step={item} expected={renderTemplate(item.validation_value, item)} />}
                    {open && <CaptureBox step={item} />}
                    {item.logs && item.logs.length > 0 && (
                      <Box color="text-status-error" fontSize="body-s">
                        {item.logs}
                      </Box>
                    )}
                  </SpaceBetween>
                </StepCell>
              );
            },
          },
        ]}
        items={tableItems}
        variant="container"
        stripedRows
        empty={<Box textAlign="center" padding="l">No steps found</Box>}
      />

      {/* Trace HTML Viewer Modal */}
      <Modal
        visible={traceModalVisible}
        onDismiss={handleCloseModal}
        header={traceTitle}
        size="max"
      >
        {traceLoading && (
          <Box textAlign="center" padding="l">
            <StatusIndicator type="loading">Loading trace...</StatusIndicator>
          </Box>
        )}
        {traceError && (
          <Box textAlign="center" padding="l" color="text-status-error">
            {traceError}
          </Box>
        )}
        {traceUrl && !traceLoading && (
          <iframe
            src={traceUrl}
            title="Nova Act Trace Viewer"
            style={{
              width: '100%',
              height: '80vh',
              border: 'none',
              borderRadius: '4px',
            }}
          />
        )}
      </Modal>
    </>
  );
}
