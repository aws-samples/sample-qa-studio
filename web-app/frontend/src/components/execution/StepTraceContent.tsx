import React from 'react';
import Grid from '@cloudscape-design/components/grid';
import Box from '@cloudscape-design/components/box';
import Spinner from '@cloudscape-design/components/spinner';
import Alert from '@cloudscape-design/components/alert';
import SpaceBetween from '@cloudscape-design/components/space-between';

export interface TraceStepRequest {
  screenshot?: string; // base64 encoded PNG
}

export interface TraceStepResponse {
  rawProgramBody?: string;
}

export interface TraceStep {
  request?: TraceStepRequest;
  response?: TraceStepResponse;
  screenshotWithBbox?: string; // data URI with bounding box overlay
}

export interface StepTraceContentProps {
  traceSteps: TraceStep[];
  loading: boolean;
  error: string | null;
}

export default function StepTraceContent({
  traceSteps,
  loading,
  error,
}: StepTraceContentProps) {
  if (loading) {
    return (
      <Box textAlign="center" padding="l">
        <Spinner size="large" />
      </Box>
    );
  }

  if (error) {
    return <Alert type="error">{error}</Alert>;
  }

  if (traceSteps.length === 0) {
    return (
      <Box color="text-status-inactive" textAlign="center" padding="s">
        No trace steps available
      </Box>
    );
  }

  return (
    <SpaceBetween size="l">
      {traceSteps.map((step, index) => {
        const screenshot = step.screenshotWithBbox || step.request?.screenshot;
        const action = step.response?.rawProgramBody;
        const stepNum = index + 1;

        return (
          <div key={stepNum}>
            <Box fontWeight="bold" padding={{ bottom: 'xs' }}>
              Sub-step {stepNum}
            </Box>
            <Grid
              gridDefinition={[
                { colspan: { default: 12, m: 6 } },
                { colspan: { default: 12, m: 6 } },
              ]}
            >
              {/* Screenshot column */}
              <div>
                {screenshot ? (
                  <img
                    src={screenshot}
                    alt={`Screenshot for sub-step ${stepNum}`}
                    style={{ width: '100%', borderRadius: '4px', border: '1px solid #d5dbdb' }}
                  />
                ) : (
                  <Box
                    color="text-status-inactive"
                    textAlign="center"
                    padding="l"
                    fontSize="body-s"
                  >
                    Screenshot unavailable
                  </Box>
                )}
              </div>

              {/* Details column */}
              <SpaceBetween size="s">
                <div>
                  <Box fontWeight="bold" fontSize="body-s" color="text-label">
                    Action
                  </Box>
                  <Box fontSize="body-s">
                    {action ? (
                      <code style={{ fontSize: '12px', background: 'transparent', padding: '2px 6px', borderRadius: '4px', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                        {action}
                      </code>
                    ) : (
                      'Not available'
                    )}
                  </Box>
                </div>
              </SpaceBetween>
            </Grid>
          </div>
        );
      })}
    </SpaceBetween>
  );
}
