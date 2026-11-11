/**
 * Dataset grid editor for `repeat` steps.
 *
 * Dumb component: it owns no dataset state. `columns` / `rows` come in,
 * every edit goes out through `onChange({ columns, rows })`. Validation
 * lives in repeatDatasetArgs.ts and is surfaced as FormField errorText so
 * the parent (StepFormModal) can disable Save on the same predicate.
 *
 * Layout: a header row of column-name inputs (rename / remove / add), one
 * row of cell inputs per dataset row (remove / add), and a "Paste CSV"
 * expandable section that replaces the whole grid after confirmation.
 */

import { useState } from 'react';
import Box from '@cloudscape-design/components/box';
import Button from '@cloudscape-design/components/button';
import ExpandableSection from '@cloudscape-design/components/expandable-section';
import FormField from '@cloudscape-design/components/form-field';
import Input from '@cloudscape-design/components/input';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Textarea from '@cloudscape-design/components/textarea';
import Alert from '@cloudscape-design/components/alert';

import {
  MAX_REPEAT_COLUMNS,
  MAX_REPEAT_ROWS,
  parseCsvText,
  validateRepeatDataset,
  type RepeatDataset,
} from './repeatDatasetArgs';

interface RepeatDatasetEditorProps {
  columns: string[];
  rows: string[][];
  onChange: (dataset: RepeatDataset) => void;
}

export default function RepeatDatasetEditor({ columns, rows, onChange }: RepeatDatasetEditorProps) {
  const [csvText, setCsvText] = useState('');
  const [csvConfirmPending, setCsvConfirmPending] = useState(false);
  const errors = validateRepeatDataset(columns, rows);

  const renameColumn = (index: number, name: string) => {
    const next = [...columns];
    next[index] = name;
    onChange({ columns: next, rows });
  };

  const addColumn = () => {
    const base = 'column';
    let candidate = `${base}${columns.length + 1}`;
    let suffix = columns.length + 1;
    while (columns.includes(candidate)) {
      suffix += 1;
      candidate = `${base}${suffix}`;
    }
    onChange({
      columns: [...columns, candidate],
      rows: rows.map((row) => [...row, '']),
    });
  };

  const removeColumn = (index: number) => {
    onChange({
      columns: columns.filter((_, i) => i !== index),
      rows: rows.map((row) => row.filter((_, i) => i !== index)),
    });
  };

  const setCell = (rowIndex: number, columnIndex: number, value: string) => {
    const nextRows = rows.map((row, r) => (r === rowIndex ? row.map((cell, c) => (c === columnIndex ? value : cell)) : row));
    onChange({ columns, rows: nextRows });
  };

  const addRow = () => {
    onChange({ columns, rows: [...rows, columns.map(() => '')] });
  };

  const removeRow = (rowIndex: number) => {
    onChange({ columns, rows: rows.filter((_, r) => r !== rowIndex) });
  };

  const applyCsv = () => {
    const parsed = parseCsvText(csvText);
    onChange(parsed);
    setCsvText('');
    setCsvConfirmPending(false);
  };

  const parsedPreview = csvText.trim() ? parseCsvText(csvText) : null;

  return (
    <SpaceBetween direction="vertical" size="m">
      <FormField
        stretch
        label="Dataset"
        description={`Each column becomes a {{column}} variable inside the repeat; the steps inside run once per row. Up to ${MAX_REPEAT_COLUMNS} columns and ${MAX_REPEAT_ROWS} rows.`}
        errorText={errors.length > 0 ? errors.join('; ') : undefined}
      >
        <div role="table" aria-label="Repeat dataset" data-testid="repeat-dataset-grid">
          <div role="row" style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginBottom: 8 }}>
            {columns.map((column, columnIndex) => (
              <div role="columnheader" key={`col-${columnIndex}`} style={{ flex: 1, minWidth: 120 }}>
                <SpaceBetween direction="horizontal" size="xxs">
                  <Input
                    value={column}
                    ariaLabel={`Column ${columnIndex + 1} name`}
                    placeholder="column_name"
                    onChange={({ detail }) => renameColumn(columnIndex, detail.value)}
                  />
                  <Button
                    variant="icon"
                    iconName="close"
                    ariaLabel={`Remove column ${column || columnIndex + 1}`}
                    disabled={columns.length <= 1}
                    onClick={() => removeColumn(columnIndex)}
                  />
                </SpaceBetween>
              </div>
            ))}
            <Button
              iconName="add-plus"
              ariaLabel="Add column"
              disabled={columns.length >= MAX_REPEAT_COLUMNS}
              onClick={addColumn}
            >
              Column
            </Button>
          </div>

          {rows.map((row, rowIndex) => (
            <div role="row" key={`row-${rowIndex}`} style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
              {columns.map((column, columnIndex) => (
                <div role="cell" key={`cell-${rowIndex}-${columnIndex}`} style={{ flex: 1, minWidth: 120 }}>
                  <Input
                    value={row[columnIndex] ?? ''}
                    ariaLabel={`Row ${rowIndex + 1}, ${column || `column ${columnIndex + 1}`}`}
                    onChange={({ detail }) => setCell(rowIndex, columnIndex, detail.value)}
                  />
                </div>
              ))}
              <Button
                variant="icon"
                iconName="remove"
                ariaLabel={`Remove row ${rowIndex + 1}`}
                disabled={rows.length <= 1}
                onClick={() => removeRow(rowIndex)}
              />
            </div>
          ))}
        </div>
        <Box margin={{ top: 'xs' }}>
          <Button iconName="add-plus" ariaLabel="Add row" disabled={rows.length >= MAX_REPEAT_ROWS} onClick={addRow}>
            Row
          </Button>
        </Box>
      </FormField>

      <ExpandableSection headerText="Paste CSV" variant="footer">
        <SpaceBetween direction="vertical" size="s">
          <FormField
            stretch
            label="CSV"
            description="First line = column names, following lines = rows. Replaces the current dataset."
          >
            <Textarea
              value={csvText}
              ariaLabel="CSV text"
              placeholder={'email,role\nalice@example.com,admin\nbob@example.com,viewer'}
              rows={4}
              onChange={({ detail }) => {
                setCsvText(detail.value);
                setCsvConfirmPending(false);
              }}
            />
          </FormField>
          {csvConfirmPending && parsedPreview && (
            <Alert
              type="warning"
              header="Replace the current dataset?"
              action={
                <Button onClick={applyCsv} data-testid="confirm-replace-csv">
                  Replace
                </Button>
              }
            >
              This replaces {columns.length} column{columns.length === 1 ? '' : 's'} and {rows.length} row
              {rows.length === 1 ? '' : 's'} with {parsedPreview.columns.length} column
              {parsedPreview.columns.length === 1 ? '' : 's'} and {parsedPreview.rows.length} row
              {parsedPreview.rows.length === 1 ? '' : 's'} from the CSV.
            </Alert>
          )}
          {!csvConfirmPending && (
            <Button disabled={!parsedPreview || parsedPreview.columns.length === 0} onClick={() => setCsvConfirmPending(true)}>
              Replace dataset with CSV
            </Button>
          )}
        </SpaceBetween>
      </ExpandableSection>
    </SpaceBetween>
  );
}
