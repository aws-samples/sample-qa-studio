import React from 'react';
import { useNavigate } from 'react-router-dom';
import Box from '@cloudscape-design/components/box';
import Link from '@cloudscape-design/components/link';
import Table from '@cloudscape-design/components/table';
import { ApplicationUsecaseCost, CostSummary, costsApi } from '../../../utils/api';
import { CostTrend, formatUsd } from './CostTrend';
import { LoadedCostCard } from './LoadedCostCard';
import { useCosts } from './useCosts';

const NO_DATA = <Box color="text-body-secondary">No data</Box>;

/** 1d / 7d cells: the billed amount only. */
function amountCell(summary: CostSummary | null, window: '1d' | '7d') {
  if (summary === null) return NO_DATA;
  return formatUsd(summary[`window_${window}`]);
}

/** 30d cell: billed amount plus the trend arrow and percentage. */
function trendCell(summary: CostSummary | null) {
  if (summary === null) return NO_DATA;
  return (
    <CostTrend
      amount={summary.window_30d}
      trend={summary.window_30d_trend}
      changePct={summary.window_30d_change_pct}
      variant="inline"
    />
  );
}

function UsecaseCostTable({ usecases }: { usecases: ApplicationUsecaseCost[] }) {
  const navigate = useNavigate();
  return (
    <Table
      variant="embedded"
      items={usecases}
      trackBy="usecase_id"
      // No sortingField: a sortable header renders as role="button" and breaks
      // the read-only assertions; rows stay in API order (30d cost descending).
      columnDefinitions={[
        {
          id: 'name',
          header: 'Use case',
          cell: (item) => (
            <Link href={`/usecase/${item.usecase_id}`} onFollow={(e) => { e.preventDefault(); navigate(`/usecase/${item.usecase_id}`); }}>
              {item.name}
            </Link>
          ),
        },
        { id: 'window_1d', header: 'Last day', cell: (item) => amountCell(item.summary, '1d') },
        { id: 'window_7d', header: 'Last 7 days', cell: (item) => amountCell(item.summary, '7d') },
        { id: 'window_30d', header: 'Last 30 days', cell: (item) => trendCell(item.summary) },
      ]}
      empty={<Box textAlign="center" color="text-body-secondary" padding="s">No use cases with cost data</Box>}
    />
  );
}

interface ApplicationCostCardProps {
  applicationId: string;
}

/** "Cost" card for the application detail page: windows, sparkline and the per-use-case table. */
export default function ApplicationCostCard({ applicationId }: ApplicationCostCardProps) {
  const state = useCosts(costsApi.application, applicationId);
  return (
    <LoadedCostCard state={state}>
      {state.data && <UsecaseCostTable usecases={state.data.usecases} />}
    </LoadedCostCard>
  );
}
