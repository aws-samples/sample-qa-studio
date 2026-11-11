import type { StatusIndicatorProps } from '@cloudscape-design/components/status-indicator';

/**
 * Map an execution status ("success", "failed", "running", …) to a Cloudscape
 * StatusIndicator type. Unknown statuses render as "pending".
 *
 * Views with extra statuses (step "cached", suite "partial") keep their own
 * mapping.
 */
export function executionStatusType(status: string): StatusIndicatorProps.Type {
  switch (status) {
    case 'success': return 'success';
    case 'error':
    case 'failed': return 'error';
    case 'running':
    case 'executing': return 'in-progress';
    case 'pending': return 'pending';
    case 'stopped': return 'stopped';
    default: return 'pending';
  }
}
