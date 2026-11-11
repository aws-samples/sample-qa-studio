import Badge from '@cloudscape-design/components/badge';
import './StepTypeBadge.css';

interface StepTypeBadgeProps {
  stepType?: string;
}

/**
 * The step type badge shared by the step cards (`WorkflowStepsCard`) and the
 * Execution Steps table. A missing or unknown step type renders as Navigation,
 * the runner's default.
 */
export default function StepTypeBadge({ stepType }: StepTypeBadgeProps) {
  switch (stepType) {
    case 'secret':
      return <Badge color="red">Secret</Badge>;
    case 'validation':
      return <Badge color="green">Validation</Badge>;
    case 'assertion':
      return <Badge color="green">Assertion</Badge>;
    case 'retrieve_value':
      return <Badge color="blue">Value</Badge>;
    case 'url':
      return <Badge color="severity-medium">Goto (deprecated)</Badge>;
    case 'browser':
      return <Badge color="severity-medium">Browser</Badge>;
    case 'transform':
      return <Badge color="blue">Transform</Badge>;
    case 'download':
      return <Badge className="badge-purple">Download</Badge>;
    case 'network_assertion':
      return <Badge color="blue">Network</Badge>;
    case 'repeat':
      return <Badge color="severity-low">Repeat</Badge>;
    case 'navigation':
    default:
      return <Badge>Navigation</Badge>;
  }
}
