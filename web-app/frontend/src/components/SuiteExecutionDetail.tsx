import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import Box from "@cloudscape-design/components/box";
import AppLayout from "@cloudscape-design/components/app-layout";
import Container from "@cloudscape-design/components/container";
import Grid from "@cloudscape-design/components/grid";
import Table from "@cloudscape-design/components/table";
import StatusIndicator from "@cloudscape-design/components/status-indicator";
import Link from "@cloudscape-design/components/link";
import KeyValuePairs from "@cloudscape-design/components/key-value-pairs";
import CopyToClipboard from "@cloudscape-design/components/copy-to-clipboard";
import PieChart from "@cloudscape-design/components/pie-chart";
import { testSuites, SuiteArtifact } from '../utils/api';
import { formatDateTime } from '../utils/dateFormat';
import { SuiteExecution } from '../utils/api';
import Breadcrumb from './common/Breadcrumb';
import LogViewer from './common/LogViewer';

function formatDuration(ms?: number): string {
  if (!ms) return '-';

  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;

  if (hours > 0) {
    return `${hours}h ${minutes}m ${secs}s`;
  } else if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  } else {
    return `${secs}s`;
  }
}

function formatTimestamp(timestamp?: string): string {
  return formatDateTime(timestamp);
}

function getStatusIndicator(status: string) {
  const getStatusType = (status: string) => {
    switch (status) {
      case 'success': return 'success';
      case 'error':
      case 'failed': return 'error';
      case 'running':
      case 'executing': return 'in-progress';
      case 'pending': return 'pending';
      case 'completed': return 'success';
      case 'running': return 'in-progress';
      case 'partial': return 'warning';
      default: return 'info';
    }
  };

  return (
    <StatusIndicator type={getStatusType(status)}>
      {status}
    </StatusIndicator>
  );
}

export default function SuiteExecutionDetail() {
  const { suiteId, executionId } = useParams();
  const navigate = useNavigate();
  const [execution, setExecution] = useState<SuiteExecution | null>(null);
  const [loading, setLoading] = useState(true);
  const [logDownloadUrl, setLogDownloadUrl] = useState<string | null>(null);
  const [artifactsLoading, setArtifactsLoading] = useState(true);

  const fetchExecution = async () => {
    if (!suiteId || !executionId) return;
    
    try {
      const data = await testSuites.getExecution(suiteId, executionId);
      setExecution(data);
    } catch (error) {
      console.error('Failed to fetch execution:', error);
    } finally {
      setLoading(false);
    }
  };

  // Initial data fetch
  useEffect(() => {
    fetchExecution();
  }, [suiteId, executionId]);

  // Polling effect for running status
  useEffect(() => {
    let intervalId: NodeJS.Timeout | null = null;

    if (execution?.status === 'running') {
      intervalId = setInterval(() => {
        fetchExecution();
      }, 5000); // 5 seconds
    }

    // Cleanup interval on unmount or when status changes
    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [execution?.status, suiteId, executionId]);

  // Fetch suite artifacts for log viewing
  useEffect(() => {
    const fetchArtifacts = async () => {
      if (!suiteId || !executionId) return;
      try {
        setArtifactsLoading(true);
        const data = await testSuites.listArtifacts(suiteId, executionId);
        const logArtifact = (data.artifacts || []).find(
          (a: SuiteArtifact) => a.type === 'logs'
        );
        setLogDownloadUrl(logArtifact?.download_url ?? null);
      } catch (error) {
        console.error('Failed to fetch suite artifacts:', error);
        setLogDownloadUrl(null);
      } finally {
        setArtifactsLoading(false);
      }
    };

    // Only fetch artifacts when execution is no longer running
    if (execution && execution.status !== 'running' && execution.status !== 'pending') {
      fetchArtifacts();
    }
  }, [suiteId, executionId, execution?.status]);

  const handleRerunSuite = async () => {
    if (!suiteId) return;
    
    try {
      const response = await testSuites.execute(suiteId);
      navigate(`/test-suites/${suiteId}/executions/${response.suite_execution_id}`);
    } catch (error) {
      console.error('Failed to re-run suite:', error);
    }
  };

  if (loading) return <div>Loading...</div>;
  if (!execution) return <div>Execution not found</div>;
  if (!suiteId || !executionId) return <div>Invalid parameters</div>;

  return (
    <AppLayout
      navigationHide
      toolsHide
      content={
        <SpaceBetween direction="vertical" size="l">
          <Breadcrumb
            items={[
              { text: "Home", href: "/" },
              { text: "Test Suites", href: "/test-suites" },
              { text: execution.suite_name, href: `/test-suites/${suiteId}` },
              { text: "Execution Details" }
            ]}
          />
          
          <Header 
            variant="h1"
            actions={
              (execution.status === 'completed' || execution.status === 'partial' || execution.status === 'failed') && (
                <Button
                  iconName="refresh"
                  onClick={handleRerunSuite}
                >
                  Re-run Suite
                </Button>
              )
            }
          >
            Suite Execution Details
          </Header>

          {/* Execution Information and Summary */}
          <Grid
            gridDefinition={[
              { colspan: { default: 12, m: 9 } },
              { colspan: { default: 12, m: 3 } },
            ]}
          >
            <Container 
              header={
                <Header variant="h2">Suite Execution Information</Header>
              }
            >
              <KeyValuePairs
                columns={2}
                items={[
                  {
                    label: "Execution ID",
                    value: (
                      <CopyToClipboard
                        copyButtonAriaLabel="Copy Execution ID"
                        copyErrorText="failed to copy"
                        copySuccessText="copied"
                        textToCopy={execution.id}
                        variant="inline"
                      />
                    ),
                  },
                  {
                    label: "Status",
                    value: getStatusIndicator(execution.status),
                  },
                  {
                    label: "Suite Name",
                    value: <Link href={`/test-suites/${suiteId}`}>{execution.suite_name}</Link>,
                  },
                  {
                    label: "Trigger Type",
                    value: execution.trigger_type,
                  },
                  {
                    label: "Started At",
                    value: formatTimestamp(execution.started_at),
                  },
                  {
                    label: "Completed At",
                    value: formatTimestamp(execution.completed_at),
                  },
                  {
                    label: "Duration",
                    value: formatDuration(execution.duration_ms),
                  },
                  {
                    label: "Triggered By",
                    value: execution.triggered_by || '-',
                  },
                ]}
              />
            </Container>

            <Container
              header={
                <Header variant="h2">Summary</Header>
              }
            >
              <PieChart
                data={[
                  {
                    title: "Successful",
                    value: execution.successful_usecases,
                    color: "#037f0c"
                  },
                  {
                    title: "Failed",
                    value: execution.failed_usecases,
                    color: "#d13212"
                  },
                  {
                    title: "Running",
                    value: execution.running_usecases,
                    color: "#0972d3"
                  }
                ].filter(item => item.value > 0)}
                detailPopoverContent={(datum, sum) => [
                  { key: "Tests", value: datum.value },
                  { key: "Percentage", value: `${((datum.value / sum) * 100).toFixed(1)}%` }
                ]}
                segmentDescription={(datum, sum) => 
                  `${datum.value} tests, ${((datum.value / sum) * 100).toFixed(1)}%`
                }
                ariaLabel="Test execution status"
                ariaDescription="Donut chart showing the distribution of test execution results"
                size="small"
                variant="donut"
                innerMetricValue={execution.total_usecases.toString()}
                innerMetricDescription="Total Tests"
                hideFilter
                hideLegend={false}
                empty={
                  <Box textAlign="center" color="inherit">
                    <b>No data available</b>
                  </Box>
                }
              />
            </Container>
          </Grid>

          {/* Results Table */}
          <Table
            columnDefinitions={[
              {
                id: 'usecase_name',
                header: 'Name',
                cell: (item) => (
                  <Link href={`/usecase/${item.usecase_id}`}>
                    {item.usecase_name || 'Unknown Use Case'}
                  </Link>
                ),
                sortingField: 'usecase_name',
                width: 300
              },
              {
                id: 'status',
                header: 'Status',
                cell: (item) => getStatusIndicator(item.status),
                sortingField: 'status',
                width: 150
              },
              {
                id: 'started_at',
                header: 'Started',
                cell: (item) => formatTimestamp(item.created_at),
                sortingField: 'created_at',
                width: 200
              },
              {
                id: 'completed_at',
                header: 'Completed',
                cell: (item) => formatTimestamp(item.completed_at),
                sortingField: 'completed_at',
                width: 200
              },
              {
                id: 'actions',
                header: 'Actions',
                cell: (item) => (
                  item.usecase_execution_id ? (
                    <Link
                      href={`/usecase/${item.usecase_id}/execution/${item.usecase_execution_id}`}
                    >
                      View Details
                    </Link>
                  ) : (
                    <Box color="text-status-inactive">No execution</Box>
                  )
                ),
                width: 150
              },
            ]}
            items={execution.results || []}
            loadingText="Loading results"
            sortingDisabled={false}
            empty={
              <Box textAlign="center" color="inherit">
                <b>No results</b>
                <Box padding={{ bottom: 's' }} variant="p" color="inherit">
                  No use case results found for this execution.
                </Box>
              </Box>
            }
            header={
              <Header
                variant="h2"
                counter={`(${execution.results?.length || 0})`}
              >
                Use Case Results
              </Header>
            }
          />

          {/* Suite Logs */}
          {(artifactsLoading || logDownloadUrl) && (
            <Container
              header={<Header variant="h2">Suite Logs</Header>}
            >
              <LogViewer downloadUrl={logDownloadUrl} loading={artifactsLoading} />
            </Container>
          )}
        </SpaceBetween>
      }
    />
  );
}
