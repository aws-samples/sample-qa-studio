import React, { useState } from 'react';
import Table from '@cloudscape-design/components/table';
import Link from '@cloudscape-design/components/link';
import Box from '@cloudscape-design/components/box';
import Badge from '@cloudscape-design/components/badge';
import SpaceBetween from '@cloudscape-design/components/space-between';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import TextFilter from '@cloudscape-design/components/text-filter';
import { TestSuite } from '../../utils/api';

function formatLastRun(time?: string): string {
  if (!time) return 'Never';
  const date = new Date(time);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

function getStatusIndicator(suite: TestSuite) {
  if (!suite.last_execution_status) {
    return <StatusIndicator type="stopped">Never run</StatusIndicator>;
  }
  switch (suite.last_execution_status) {
    case 'completed':
      return <StatusIndicator type="success">Completed</StatusIndicator>;
    case 'partial':
      return <StatusIndicator type="warning">Partial</StatusIndicator>;
    case 'failed':
      return <StatusIndicator type="error">Failed</StatusIndicator>;
    default:
      return <StatusIndicator type="info">{suite.last_execution_status}</StatusIndicator>;
  }
}

interface TestSuitesTableProps {
  items: TestSuite[];
  loading?: boolean;
  selectedItems?: TestSuite[];
  onSelectionChange?: (items: TestSuite[]) => void;
  selectionType?: 'multi' | 'single';
  header?: React.ReactNode;
  empty?: React.ReactNode;
  showFilter?: boolean;
  showTags?: boolean;
}

export function TestSuitesTable({
  items,
  loading = false,
  selectedItems,
  onSelectionChange,
  selectionType,
  header,
  empty,
  showFilter = true,
  showTags = true,
}: TestSuitesTableProps) {
  const [filteringText, setFilteringText] = useState('');

  const filteredItems = items.filter(suite => {
    if (!filteringText) return true;
    const searchText = filteringText.toLowerCase();
    return (
      suite.name?.toLowerCase().includes(searchText) ||
      suite.description?.toLowerCase().includes(searchText) ||
      suite.tags?.some(tag => tag?.toLowerCase().includes(searchText))
    );
  });

  const columnDefinitions: any[] = [
    {
      id: 'name',
      header: 'Name',
      cell: (suite: TestSuite) => (
        <div>
          <div style={{ fontWeight: 500 }}>
            <Link href={`/test-suites/${suite.id}`}>{suite.name}</Link>
          </div>
          {suite.description && (
            <div style={{ fontSize: '0.85em', color: '#5f6b7a', marginTop: '4px' }}>
              {suite.description}
            </div>
          )}
        </div>
      ),
      sortingField: 'name',
      minWidth: 200,
    },
  ];

  if (showTags) {
    columnDefinitions.push({
      id: 'tags',
      header: 'Tags',
      cell: (suite: TestSuite) => {
        if (!suite.tags || suite.tags.length === 0) {
          return <Box color="text-status-inactive">No tags</Box>;
        }
        return (
          <SpaceBetween direction="horizontal" size="xxs">
            {suite.tags.slice(0, 3).map((tag) => (
              <Badge key={tag}>{tag}</Badge>
            ))}
            {suite.tags.length > 3 && <Badge>+{suite.tags.length - 3}</Badge>}
          </SpaceBetween>
        );
      },
      width: 180,
    });
  }

  columnDefinitions.push(
    {
      id: 'total_tests',
      header: 'Tests',
      cell: (suite: TestSuite) => suite.total_usecases || 0,
      sortingField: 'total_usecases',
      width: 80,
    },
    {
      id: 'last_run',
      header: 'Last Run',
      cell: (suite: TestSuite) => formatLastRun(suite.last_execution_time),
      sortingField: 'last_execution_time',
      width: 120,
    },
    {
      id: 'status',
      header: 'Status',
      cell: (suite: TestSuite) => getStatusIndicator(suite),
      width: 120,
    }
  );

  return (
    <Table
      columnDefinitions={columnDefinitions}
      items={filteredItems}
      trackBy="id"
      variant="embedded"
      loading={loading}
      loadingText="Loading test suites..."
      empty={empty || (filteringText ? `No test suites match "${filteringText}"` : 'No test suites found')}
      filter={showFilter ? (
        <TextFilter
          filteringText={filteringText}
          onChange={({ detail }) => setFilteringText(detail.filteringText)}
          filteringPlaceholder="Search by name, description, or tags"
          countText={`${filteredItems.length} ${filteredItems.length === 1 ? 'match' : 'matches'}`}
        />
      ) : undefined}
      selectionType={selectionType}
      selectedItems={selectedItems}
      onSelectionChange={onSelectionChange ? ({ detail }) => onSelectionChange(detail.selectedItems as TestSuite[]) : undefined}
      header={header}
      resizableColumns
    />
  );
}
