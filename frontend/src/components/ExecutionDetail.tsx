import React, { useState, useEffect, Suspense } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import KeyValuePairs from "@cloudscape-design/components/key-value-pairs";
import Table from "@cloudscape-design/components/table";
import StatusIndicator from "@cloudscape-design/components/status-indicator";
import CopyToClipboard from "@cloudscape-design/components/copy-to-clipboard";
import Modal from "@cloudscape-design/components/modal";
import Box from "@cloudscape-design/components/box";
import AppLayout from "@cloudscape-design/components/app-layout";
import { api } from '../utils/api';
import { getS3FileUrl, getVideoUrl } from '../utils/s3Utils';
import Grid from "@cloudscape-design/components/grid";
import ExecutionTimeline from './common/ExecutionTimeline';
import StatusIndicatorCompact from './common/StatusIndicatorCompact';
import ValidationResult from './common/ValidationResult';
import Breadcrumb from './common/Breadcrumb';
// import CodeView from "@cloudscape-design/code-view/code-view";

// Lazy load CodeView component since it's heavy
const CodeView = React.lazy(() => import('@cloudscape-design/code-view/code-view'));

export default function ExecutionDetail() {
  const { usecaseId, executionId } = useParams();
  const navigate = useNavigate();
  const [execution, setExecution] = useState<any>(null);
  const [usecase, setUsecase] = useState<any>(null);
  const [executionSteps, setExecutionSteps] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalVisible, setModalVisible] = useState(false);
  const [modalContent, setModalContent] = useState<{ url: string, title: string, fileType?: string } | null>(null);
  const [loadingModal, setLoadingModal] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [executionData, stepsData, usecaseData] = await Promise.all([
          api.get(`usecase/${usecaseId}/executions/${executionId}`),
          api.get(`usecase/${usecaseId}/executions/${executionId}/steps`),
          api.get(`usecase/${usecaseId}`)
        ]);

        setExecution(executionData);
        setUsecase(usecaseData);

        // Sort steps by sort property and set them
        const sortedSteps = (stepsData.steps || []).sort((a: any, b: any) => a.sort - b.sort);
        setExecutionSteps(sortedSteps);

        sortedSteps.forEach((step: any) => {
          if (step.logs.length > -1) {
            step.logs = step.logs.reverse();
          }
        })
      } catch (error) {
        console.error('Failed to fetch execution data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [usecaseId, executionId]);

  if (loading) return <div>Loading...</div>;
  if (!execution) return <div>Execution not found</div>;

  return (
    <AppLayout
      navigationHide
      toolsHide
      content={
        <SpaceBetween direction="vertical" size="l">
          <Breadcrumb
            items={[
              { text: "Home", href: "/" },
              { text: usecase?.name || "Use Case", href: `/usecase/${usecaseId}` },
              { text: "Execution Details" }
            ]}
          />
          <Header variant="h1">
            Execution Details
          </Header>

          <Grid
            gridDefinition={[{ colspan: 9 }, { colspan: 3 }]}
          >
            <SpaceBetween direction="vertical" size="m">
              <Container header={<Header variant="h2">Execution Information</Header>}>
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
                          textToCopy={execution.sk.replace('EXECUTION#', '')}
                          variant="inline"
                        />
                      ),
                    },
                    {
                      label: "Status",
                      value: <StatusIndicator type={execution.status}>
                        {execution.status}
                      </StatusIndicator>,
                    },
                    {
                      label: "Created",
                      value: new Date(execution.createdAt).toLocaleString(),
                    },
                    {
                      label: "Starting URL",
                      value: (<a href={execution.starting_url} target="_startPage">{execution.starting_url}</a>),
                    },
                    {
                      label: "NovaAct Session ID",
                      value: (
                        <CopyToClipboard
                          copyButtonAriaLabel="Copy NovaAct Session ID"
                          copyErrorText="failed to copy"
                          copySuccessText="copied"
                          textToCopy={execution.novaActSessionId}
                          variant="inline"
                        />
                      ),
                    },
                    {
                      label: "Recording",
                      value: execution.novaActSessionId ? (
                        <Button
                          variant="inline-link"
                          iconName="play"
                          onClick={async () => {
                            try {
                              setLoadingModal(true);
                              const { signedUrl, fileName } = await getVideoUrl(usecaseId!, executionId!);
                              setModalContent({
                                url: signedUrl,
                                title: `Execution Video`,
                                fileType: 'video'
                              });
                              setModalVisible(true);
                            } catch (error) {
                              console.error('Failed to load video file:', error);
                            } finally {
                              setLoadingModal(false);
                            }
                          }}
                        >
                          View
                        </Button>
                      ) : 'Not Available',
                    }
                  ]}
                />
              </Container>

              <Container header={<Header variant="h2">Execution Steps</Header>}>
                <Table
                  variant="embedded"
                  columnDefinitions={[
                    {
                      id: 'sort',
                      header: 'Step',
                      cell: item => item.sort,
                      maxWidth: 60,
                    },
                    {
                      id: 'status',
                      header: 'Status',
                      maxWidth: 50,
                      cell: item => {
                        const status = item.status || 'pending';
                        return (
                          <StatusIndicatorCompact status={status} />
                        );
                      },
                    },
                    {
                      id: 'instruction',
                      header: 'Instruction',
                      cell: item => item.instruction,
                      maxWidth: 150
                    },
                    {
                      id: 'actId',
                      header: 'Act ID',
                      cell: item => {
                        const actId = item.actId || item.act_id;
                        if (!actId) return 'N/A';

                        return (
                          <CopyToClipboard
                            copyButtonAriaLabel="Copy Act ID"
                            copyErrorText="failed to copy"
                            copySuccessText="copied"
                            textToCopy={actId}
                            variant="inline"
                          />
                        );
                      },
                      maxWidth: 120,
                    },
                    {
                      id: 'trace',
                      header: 'Traces',
                      cell: item => {
                        const actId = item.actId || item.act_id;
                        if (!actId) return 'N/A';

                        const handleViewFile = async () => {
                          try {
                            setLoadingModal(true);
                            const { signedUrl, fileName } = await getS3FileUrl(usecaseId!, executionId!, actId, 'html');
                            setModalContent({
                              url: signedUrl,
                              title: `Step ${item.sort}: ${fileName}`,
                              fileType: 'html'
                            });
                            setModalVisible(true);
                          } catch (error) {
                            console.error('Failed to load HTML file:', error);
                          } finally {
                            setLoadingModal(false);
                          }
                        };

                        return (
                          <Button
                            variant="icon"
                            iconName="file-open"
                            ariaLabel="View HTML file"
                            onClick={handleViewFile}
                            loading={loadingModal}
                          />
                        );
                      },
                      maxWidth: 100,
                    },
                    {
                      id: 'logs',
                      header: 'Validation',
                      cell: item => {
                        console.log(item)
                        if ((item.stepType == 'validation' || item.stepType == 'assertion') && item.actualValue) {
                          return (
                            <ValidationResult
                              validationType={item.validationType}
                              validationOperator={item.validationOperator}
                              validationValue={item.validationValue}
                              actualValue={item.actualValue}
                              status={item.status || 'pending'}
                            />
                          );
                        }

                        if(item.logs.length > 0) {
                          return (<pre>{item.logs}</pre>)
                        }

                        return null

                      },
                    },
                  ]}
                  items={executionSteps}
                  empty="No execution steps found."
                />
              </Container>
            </SpaceBetween>
            <ExecutionTimeline execution={execution} />
          </Grid>

          {/* Modal for viewing HTML files */}
          <Modal
            onDismiss={() => setModalVisible(false)}
            visible={modalVisible}
            size="max"
            header={modalContent?.title || "View File"}
            footer={
              <Box float="right">
                <SpaceBetween direction="horizontal" size="xs">
                  <Button variant="link" onClick={() => setModalVisible(false)}>
                    Close
                  </Button>
                  {modalContent?.url && (
                    <Button
                      variant="primary"
                      onClick={() => window.open(modalContent.url, '_blank')}
                      iconName="external"
                    >
                      Open in New Tab
                    </Button>
                  )}
                </SpaceBetween>
              </Box>
            }
          >
            {modalContent?.url && (
              modalContent.fileType === 'video' ? (
                <video
                  src={modalContent.url}
                  controls
                  style={{
                    width: '100%',
                    height: '80vh',
                    borderRadius: '4px'
                  }}
                  title={modalContent.title}
                />
              ) : (
                <iframe
                  src={modalContent.url}
                  style={{
                    width: '100%',
                    height: '80vh',
                    border: 'none',
                    borderRadius: '4px'
                  }}
                  title={modalContent.title}
                />
              )
            )}
          </Modal>
        </SpaceBetween>
      }
    />
  );
}