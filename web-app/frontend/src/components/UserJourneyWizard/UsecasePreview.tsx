import { useState } from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import Box from "@cloudscape-design/components/box";
import ColumnLayout from "@cloudscape-design/components/column-layout";
import Badge from "@cloudscape-design/components/badge";
import ExpandableSection from "@cloudscape-design/components/expandable-section";
import Table from "@cloudscape-design/components/table";
import TextContent from "@cloudscape-design/components/text-content";

interface GeneratedUsecase {
  exportVersion: string;
  exportedAt: string;
  usecase: {
    name: string;
    description: string;
    starting_url: string;
    active: boolean;
    region: string;
    tags: string[];
  };
  steps: Array<{
    sort: number;
    instruction: string;
    step_type: string;
    secret_key?: string;
    capture_variable?: string;
    validation_type?: string;
    validation_operator?: string;
    validation_value?: string;
    assertion_variable?: string;
    value_step?: string;
    value_type?: string;
  }>;
  variables: any[];
  secrets: any[];
  hooks: any;
}

interface UsecasePreviewProps {
  usecase: GeneratedUsecase;
  onImport: () => void;
  onRegenerate: () => void;
  isImporting: boolean;
}

export default function UsecasePreview({ usecase, onImport, onRegenerate, isImporting }: UsecasePreviewProps) {
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    steps: false,
    details: false
  });

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  const getStepTypeBadge = (stepType: string) => {
    const typeConfig = {
      navigation: { color: 'blue' as const, label: 'Navigation' },
      url: { color: 'severity-medium' as const, label: 'Goto' },
      validation: { color: 'green' as const, label: 'Validation' },
      secret: { color: 'red' as const, label: 'Secret' },
      retrieve_value: { color: 'grey' as const, label: 'Retrieve Value' },
      os_action: { color: 'severity-medium' as const, label: 'OS Action' }
    };

    const config = typeConfig[stepType as keyof typeof typeConfig] || { color: 'grey' as const, label: stepType };
    return <Badge color={config.color}>{config.label}</Badge>;
  };

  const getKeyActions = () => {
    const actionTypes = usecase.steps.reduce((acc, step) => {
      acc[step.step_type] = (acc[step.step_type] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);

    return Object.entries(actionTypes).map(([type, count]) => ({
      type,
      count,
      label: type.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())
    }));
  };

  const keyActions = getKeyActions();

  return (
    <SpaceBetween direction="vertical" size="l">
      {/* Summary Section */}
      <Container>
        <SpaceBetween direction="vertical" size="m">
          <Header variant="h2">Generated Test Case Summary</Header>
          
          <ColumnLayout columns={3} variant="text-grid">
            <div>
              <Box variant="awsui-key-label">Use Case Name</Box>
              <TextContent>
                <strong>{usecase.usecase.name}</strong>
              </TextContent>
            </div>
            <div>
              <Box variant="awsui-key-label">Total Steps</Box>
              <TextContent>
                <strong>{usecase.steps.length}</strong>
              </TextContent>
            </div>
            <div>
              <Box variant="awsui-key-label">Starting URL</Box>
              <TextContent>
                <strong>{usecase.usecase.starting_url}</strong>
              </TextContent>
            </div>
          </ColumnLayout>

          <div>
            <Box variant="awsui-key-label">Description</Box>
            <TextContent>
              <p>{usecase.usecase.description}</p>
            </TextContent>
          </div>

          {/* Key Actions Summary */}
          <div>
            <Box variant="awsui-key-label">Key Actions Summary</Box>
            <SpaceBetween direction="horizontal" size="xs">
              {keyActions.map(action => (
                <Badge key={action.type} color="blue">
                  {action.count} {action.label}{action.count !== 1 ? 's' : ''}
                </Badge>
              ))}
            </SpaceBetween>
          </div>
        </SpaceBetween>
      </Container>

      {/* Expandable Sections */}
      <SpaceBetween direction="vertical" size="m">
        {/* Steps Details */}
        <ExpandableSection
          headerText={`Test Steps (${usecase.steps.length})`}
          expanded={expandedSections.steps}
          onChange={() => toggleSection('steps')}
        >
          <Table
            variant="embedded"
            columnDefinitions={[
              {
                id: 'sort',
                header: 'Step',
                cell: item => item.sort,
                width: 60
              },
              {
                id: 'type',
                header: 'Type',
                cell: item => getStepTypeBadge(item.step_type),
                width: 120
              },
              {
                id: 'instruction',
                header: 'Instruction',
                cell: item => (
                  <TextContent>
                    <p style={{ margin: 0, wordBreak: 'break-word' }}>
                      {item.instruction}
                    </p>
                  </TextContent>
                )
              },
              {
                id: 'Validations',
                header: 'Validations',
                cell: item => {
                  const details = [];
                  if (item.validation_type) details.push(`Validation: ${item.validation_type}`);
                  if (item.validation_operator) details.push(`Operator: ${item.validation_operator}`);
                  if (item.validation_value) details.push(`Value: ${item.validation_value}`);
                  if (item.capture_variable) details.push(`Variable: ${item.capture_variable}`);
                  if (item.secret_key) details.push(`Secret: ${item.secret_key}`);
                  
                  return details.length > 0 ? (
                    <TextContent>
                      <small>{details.join(', ')}</small>
                    </TextContent>
                  ) : '-';
                },
                width: 400
              }
            ]}
            items={usecase.steps}
            loadingText="Loading steps"
            empty={
              <Box textAlign="center" color="inherit">
                <b>No steps found</b>
                <Box variant="p" color="inherit">
                  The generated use case doesn't contain any steps.
                </Box>
              </Box>
            }
          />
        </ExpandableSection>

        {/* Additional Details */}
        <ExpandableSection
          headerText="Additional Details"
          expanded={expandedSections.details}
          onChange={() => toggleSection('details')}
        >
          <ColumnLayout columns={2} variant="text-grid">
            <div>
              <Box variant="awsui-key-label">Export Version</Box>
              <TextContent>{usecase.exportVersion}</TextContent>
            </div>
            <div>
              <Box variant="awsui-key-label">Generated At</Box>
              <TextContent>{new Date(usecase.exportedAt).toLocaleString()}</TextContent>
            </div>
            <div>
              <Box variant="awsui-key-label">Active</Box>
              <Badge color={usecase.usecase.active ? 'green' : 'red'}>
                {usecase.usecase.active ? 'Yes' : 'No'}
              </Badge>
            </div>
            <div>
              <Box variant="awsui-key-label">Region</Box>
              <TextContent>{usecase.usecase.region}</TextContent>
            </div>
            <div>
              <Box variant="awsui-key-label">Tags</Box>
              <SpaceBetween direction="horizontal" size="xs">
                {usecase.usecase.tags.length > 0 ? (
                  usecase.usecase.tags.map((tag, index) => (
                    <Badge key={index} color="grey">{tag}</Badge>
                  ))
                ) : (
                  <TextContent><em>No tags</em></TextContent>
                )}
              </SpaceBetween>
            </div>
            <div>
              <Box variant="awsui-key-label">Variables</Box>
              <TextContent>{usecase.variables.length} defined</TextContent>
            </div>
            <div>
              <Box variant="awsui-key-label">Secrets</Box>
              <TextContent>{usecase.secrets.length} defined</TextContent>
            </div>
            <div>
              <Box variant="awsui-key-label">Hooks</Box>
              <TextContent>{usecase.hooks ? 'Configured' : 'None'}</TextContent>
            </div>
          </ColumnLayout>
        </ExpandableSection>
      </SpaceBetween>

      {/* Action Buttons */}
      <SpaceBetween direction="horizontal" size="xs">
        <Button 
          variant="primary" 
          onClick={onImport}
          loading={isImporting}
          disabled={isImporting}
        >
          Import Use Case
        </Button>
        <Button 
          onClick={onRegenerate}
          disabled={isImporting}
        >
          Regenerate
        </Button>
      </SpaceBetween>
    </SpaceBetween>
  );
}