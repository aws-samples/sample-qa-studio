/**
 * One application card on the unified applications page: health metrics,
 * sparkline and cost (from `dashboard/overview` + `dashboard/costs`) plus the
 * management actions of the former applications table. The footer (use cases,
 * test suites, team, URL) pins to the card bottom via Container `footer` +
 * `fitHeight`, so cards in one grid row stay aligned.
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import Box from '@cloudscape-design/components/box';
import ButtonDropdown, { ButtonDropdownProps } from '@cloudscape-design/components/button-dropdown';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import LineChart from '@cloudscape-design/components/line-chart';
import Link from '@cloudscape-design/components/link';
import SpaceBetween from '@cloudscape-design/components/space-between';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import { DashboardOverviewItem } from '../../types/application';
import { CostSummary } from '../../utils/api';
import { CostTrend } from '../common/cost/CostTrend';
import {
  formatRelativeTime,
  getPassRateColor,
  getStatusType,
  NO_COST_DATA_HINT,
} from '../dashboard/ApplicationMetricsCard';
import { usePermissions, canManageApplication } from '../../auth';
import { APPLICATION_CONFIG_PAGES, applicationConfigHref, ApplicationConfigSlug } from './applicationNav';

const COST_WINDOW_HINT = 'Allocated bill over the last 30 days, compared with the 30 days before';

export interface ApplicationCardProps {
  app: DashboardOverviewItem;
  /** 30-day cost of the application; `null` = no summary yet → "—". */
  cost: CostSummary | null;
  /** Suites associated with the application; `null` when the suites request failed → footer omits the link. */
  suiteCount: number | null;
  onDelete: (app: DashboardOverviewItem) => void;
}

export function ApplicationCard({ app, cost, suiteCount, onDelete }: ApplicationCardProps) {
  const navigate = useNavigate();
  const { isAdmin, teams } = usePermissions();
  const canManage = canManageApplication(isAdmin, teams, app.owner_team_id ?? null);

  const actionItems: ButtonDropdownProps.Items = [
    ...(canManage ? [{ id: 'edit', text: 'Edit' }] : []),
    { id: 'add-usecases', text: 'Add use cases' },
    { id: 'add-suites', text: 'Add test suites' },
    ...APPLICATION_CONFIG_PAGES.map((p) => ({ id: p.slug as string, text: p.text })),
    ...(canManage ? [{ id: 'delete', text: 'Delete' }] : []),
  ];

  const onActionClick: ButtonDropdownProps['onItemClick'] = ({ detail }) => {
    if (detail.id === 'delete') {
      onDelete(app);
      return;
    }
    if (detail.id === 'edit') {
      navigate(`/applications/${app.id}/edit`);
      return;
    }
    if (detail.id === 'add-usecases') {
      navigate(`/applications/${app.id}/add-usecases`);
      return;
    }
    if (detail.id === 'add-suites') {
      navigate(`/applications/${app.id}/add-test-suites`);
      return;
    }
    const configPage = APPLICATION_CONFIG_PAGES.find((p) => p.slug === detail.id);
    if (configPage) {
      navigate(applicationConfigHref(app.id, detail.id as ApplicationConfigSlug));
    }
  };

  return (
    <Container
      fitHeight
      data-testid="application-card"
      header={
        <Header
          variant="h2"
          description={
            <StatusIndicator type={getStatusType(app.last_execution_status)}>
              Last run: {app.last_execution_status || 'never'} {formatRelativeTime(app.last_execution_at)}
            </StatusIndicator>
          }
          actions={
            <ButtonDropdown
              variant="icon"
              expandToViewport
              ariaLabel={`Actions for ${app.name}`}
              data-testid={`application-actions-${app.id}`}
              onItemClick={onActionClick}
              items={actionItems}
            />
          }
        >
          <Link fontSize="heading-m" onFollow={(e) => { e.preventDefault(); navigate(`/applications/${app.id}`); }}>
            {app.name}
          </Link>
        </Header>
      }
      footer={
        <Box fontSize="body-s" color="text-body-secondary">
          <Link
            variant="secondary"
            fontSize="body-s"
            href={`/applications/${app.id}?tab=usecases`}
            onFollow={(e) => { e.preventDefault(); navigate(`/applications/${app.id}?tab=usecases`); }}
          >
            {app.usecase_count} use case{app.usecase_count === 1 ? '' : 's'}
          </Link>
          {suiteCount !== null && (
            <>
              {' · '}
              <Link
                variant="secondary"
                fontSize="body-s"
                href={`/applications/${app.id}?tab=test-suites`}
                onFollow={(e) => { e.preventDefault(); navigate(`/applications/${app.id}?tab=test-suites`); }}
              >
                {suiteCount} test suite{suiteCount === 1 ? '' : 's'}
              </Link>
            </>
          )}
          {' · team '}
          {isAdmin && app.owner_team_id ? (
            <Link
              variant="secondary"
              fontSize="body-s"
              href={`/admin/teams/${app.owner_team_id}`}
              onFollow={(e) => { e.preventDefault(); navigate(`/admin/teams/${app.owner_team_id}`); }}
            >
              {app.team || app.owner_team_id}
            </Link>
          ) : (
            app.team || '-'
          )}
          {' · '}
          <Link variant="secondary" fontSize="body-s" external href={app.base_url}>
            {app.base_url}
          </Link>
        </Box>
      }
    >
      <SpaceBetween size="m">
        {app.description && (
          <Box color="text-body-secondary">{app.description}</Box>
        )}

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 }}>
          <SpaceBetween direction="horizontal" size="xl">
            <div>
              <Box variant="awsui-key-label">Pass rate</Box>
              <Box variant="awsui-value-large" color={getPassRateColor(app.pass_rate || 0)}>
                {app.pass_rate || 0}%
              </Box>
            </div>
            <div>
              <Box variant="awsui-key-label">Executions</Box>
              <Box variant="awsui-value-large">{app.total_executions || 0}</Box>
            </div>
            <div>
              <Box variant="awsui-key-label">Failures</Box>
              <Box variant="awsui-value-large" color="text-status-error">
                {app.failure_count || 0}
              </Box>
            </div>
          </SpaceBetween>
          <div title={COST_WINDOW_HINT} style={{ textAlign: 'right' }}>
            <Box variant="awsui-key-label">Cost (30d)</Box>
            {cost ? (
              <CostTrend amount={cost.window_30d} trend={cost.window_30d_trend} changePct={cost.window_30d_change_pct} />
            ) : (
              <Box variant="awsui-value-large" color="text-body-secondary">
                <span title={NO_COST_DATA_HINT}>—</span>
              </Box>
            )}
          </div>
        </div>

        {app.series && app.series.dates.length > 0 ? (
          <LineChart
            height={100}
            hideFilter
            hideLegend
            series={[
              {
                title: 'Successes',
                type: 'line',
                data: app.series.dates.map((d, i) => ({ x: new Date(d), y: app.series!.successes[i] || 0 })),
                color: '#1d8102',
              },
              {
                title: 'Failures',
                type: 'line',
                data: app.series.dates.map((d, i) => ({ x: new Date(d), y: app.series!.failures[i] || 0 })),
                color: '#d13212',
              },
            ]}
            xDomain={[new Date(app.series.dates[0]), new Date(app.series.dates[app.series.dates.length - 1])]}
            yDomain={[0, Math.max(...app.series.successes, ...app.series.failures, 1)]}
            xScaleType="time"
            i18nStrings={{}}
            empty="No data"
          />
        ) : (
          <Box textAlign="center" color="text-body-secondary" padding={{ vertical: 'm' }}>
            No executions yet
          </Box>
        )}
      </SpaceBetween>
    </Container>
  );
}
