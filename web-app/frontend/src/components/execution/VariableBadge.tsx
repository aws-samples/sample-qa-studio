/**
 * Renders resolved step templates (`instruction` / `validation_value`) in the
 * Execution Steps table: text as-is, every `{{name}}` as a dark blue badge with
 * a small `VAR` label and the value in its original casing. Segments come from
 * `variableTokens.ts`; this module only renders.
 */
import Badge from '@cloudscape-design/components/badge';
import type { TemplateSegment } from './variableTokens';
import './VariableBadge.css';

type VariableSegment = Extract<TemplateSegment, { type: 'variable' }>;

/**
 * All kinds share one dark blue (`.variable-badge`, VariableBadge.css) so they
 * stand apart from the grey Navigation step badge; the label (value or
 * uppercase italic placeholder) carries the meaning, and the kind stays
 * available as `data-kind`.
 */
export function VariableBadge({ segment }: { segment: VariableSegment }) {
  const valueClass = segment.placeholder
    ? 'variable-badge__value variable-badge__value--placeholder'
    : 'variable-badge__value';
  return (
    <Badge className="variable-badge" data-testid="variable-badge" data-kind={segment.kind}>
      <span className="variable-badge__label">VAR</span>
      <span className={valueClass} title={segment.display}>
        {segment.display}
      </span>
    </Badge>
  );
}

export function TemplateText({ segments }: { segments: TemplateSegment[] }) {
  return (
    <>
      {segments.map((segment, index) =>
        segment.type === 'text' ? (
          <span key={index}>{segment.text}</span>
        ) : (
          <VariableBadge key={index} segment={segment} />
        ),
      )}
    </>
  );
}
