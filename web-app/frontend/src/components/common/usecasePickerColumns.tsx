/**
 * Columns for the use-case variants of AddItemsPicker (suite and application).
 */
import { Badge, StatusIndicator, type TableProps } from '@cloudscape-design/components';
import { executionStatusType } from '../../utils/executionStatus';
import { formatTimeAgo } from '../../utils/time';
import { PickerNameCell } from './AddItemsPicker';

export interface PickerUsecase {
  id: string;
  name: string;
  description?: string;
  tags?: string[];
  active?: boolean;
  last_execution_status?: string;
  last_execution_time?: string;
}

export function usecasePickerColumns<T extends PickerUsecase>(
  isAlreadyAdded: (item: T) => boolean,
  alreadyAddedLabel: string,
): TableProps.ColumnDefinition<T>[] {
  return [
    {
      id: 'name',
      header: 'Name',
      minWidth: 450,
      cell: (item) => (
        <PickerNameCell
          name={item.name}
          href={`/usecase/${item.id}`}
          description={item.description}
          alreadyAddedLabel={isAlreadyAdded(item) ? alreadyAddedLabel : undefined}
        />
      ),
    },
    {
      id: 'last_execution_status',
      header: 'Last Status',
      width: 120,
      cell: (item) =>
        item.last_execution_status ? (
          <StatusIndicator type={executionStatusType(item.last_execution_status)}>
            {item.last_execution_status}
          </StatusIndicator>
        ) : (
          <StatusIndicator type="stopped">Never run</StatusIndicator>
        ),
    },
    {
      id: 'last_execution_time',
      header: 'Last Execution',
      width: 120,
      cell: (item) =>
        item.last_execution_time ? (
          <span title={new Date(item.last_execution_time).toLocaleString()} style={{ fontSize: '0.9em' }}>
            {formatTimeAgo(item.last_execution_time)}
          </span>
        ) : (
          '-'
        ),
    },
    {
      id: 'active',
      header: 'Active',
      width: 100,
      cell: (item) =>
        item.active ? <Badge color="green">Active</Badge> : <Badge color="red">Inactive</Badge>,
    },
  ];
}
