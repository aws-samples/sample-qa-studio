import React, { useState } from 'react';
import Table from '@cloudscape-design/components/table';
import Link from '@cloudscape-design/components/link';
import Badge from '@cloudscape-design/components/badge';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import TextFilter from '@cloudscape-design/components/text-filter';
import { formatDateTime } from '../../utils/dateFormat';

export interface UsecaseItem {
  id: string;
  name: string;
  description?: string;
  active?: boolean;
  tags?: string[];
  last_execution_id?: string;
  last_execution_status?: string;
  last_execution_time?: string;
  test_platform?: string;
}

function formatTimeAgo(timestamp: string): string {
  const now = new Date();
  const past = new Date(timestamp);
  const diffMs = now.getTime() - past.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return past.toLocaleDateString();
}

function getStatusType(status: string): 'success' | 'error' | 'in-progress' | 'pending' | 'stopped' {
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

interface UsecasesTableProps {
  items: UsecaseItem[];
  loading?: boolean;
  selectedItems?: UsecaseItem[];
  onSelectionChange?: (items: UsecaseItem[]) => void;
  selectionType?: 'multi' | 'single';
  header?: React.ReactNode;
  empty?: React.ReactNode;
  showFilter?: boolean;
  showPlatform?: boolean;
}

export function UsecasesTable({
  items,
  loading = false,
  selectedItems,
  onSelectionChange,
  selectionType = 'multi',
  header,
  empty,
  showFilter = true,
  showPlatform = true,
}: UsecasesTableProps) {
  const [filteringText, setFilteringText] = useState('');

  const filteredItems = items.filter(usecase => {
    if (!filteringText) return true;
    const searchText = filteringText.toLowerCase();
    return (
      usecase.name?.toLowerCase().includes(searchText) ||
      usecase.description?.toLowerCase().includes(searchText) ||
      usecase.tags?.some(tag => tag?.toLowerCase().includes(searchText)) ||
      usecase.last_execution_status?.toLowerCase().includes(searchText)
    );
  });

  const columnDefinitions: any[] = [
    {
      id: 'name',
      header: 'Name',
      sortingField: 'name',
      minWidth: 450,
      cell: (item: UsecaseItem) => (
        <div>
          <Link href={`/usecase/${item.id}`}>{item.name}</Link>
          {item.description && (
            <div style={{ fontSize: '0.85em', color: '#5f6b7a', marginTop: '4px', whiteSpace: 'pre-line' }}>
              {item.description}
            </div>
          )}
        </div>
      ),
    },
  ];

  if (showPlatform) {
    columnDefinitions.push({
      id: 'test_platform',
      header: 'Platform',
      width: 100,
      cell: (item: UsecaseItem) => {
        const platform = item.test_platform || 'web';
        return platform === 'mobile'
          ? <Badge color="blue">Mobile</Badge>
          : <Badge color="grey">Web</Badge>;
      },
    });
  }

  columnDefinitions.push(
    {
      id: 'last_execution_status',
      header: 'Last Status',
      sortingField: 'last_execution_status',
      width: 120,
      cell: (item: UsecaseItem) => {
        if (!item.last_execution_status) {
          return <StatusIndicator type="stopped">Never run</StatusIndicator>;
        }
        return (
          <StatusIndicator type={getStatusType(item.last_execution_status)}>
            {item.last_execution_status}
          </StatusIndicator>
        );
      },
    },
    {
      id: 'last_execution_time',
      header: 'Last Execution',
      sortingField: 'last_execution_time',
      width: 120,
      cell: (item: UsecaseItem) => {
        if (!item.last_execution_time) return '-';
        const timeAgo = formatTimeAgo(item.last_execution_time);
        const fullDate = formatDateTime(item.last_execution_time);
        return (
          <span title={fullDate} style={{ fontSize: '0.9em' }}>
            {timeAgo}
          </span>
        );
      },
    },
    {
      id: 'active',
      header: 'Active',
      sortingField: 'active',
      width: 100,
      cell: (item: UsecaseItem) => item.active ? (
        <Badge color="green">Active</Badge>
      ) : (
        <Badge color="red">Inactive</Badge>
      ),
    }
  );

  return (
    <Table
      columnDefinitions={columnDefinitions}
      items={filteredItems}
      trackBy="id"
      loading={loading}
      loadingText="Loading use cases..."
      empty={empty || (filteringText ? `No use cases match "${filteringText}"` : 'No use cases found')}
      filter={showFilter ? (
        <TextFilter
          filteringText={filteringText}
          onChange={({ detail }) => setFilteringText(detail.filteringText)}
          filteringPlaceholder="Search use cases by name, description, tags, or status"
          countText={`${filteredItems.length} ${filteredItems.length === 1 ? 'match' : 'matches'}`}
        />
      ) : undefined}
      selectionType={selectionType}
      selectedItems={selectedItems}
      onSelectionChange={onSelectionChange ? ({ detail }) => onSelectionChange(detail.selectedItems as UsecaseItem[]) : undefined}
      header={header}
      resizableColumns
    />
  );
}
