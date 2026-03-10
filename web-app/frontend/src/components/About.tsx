import React from 'react';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Box from '@cloudscape-design/components/box';
import ColumnLayout from '@cloudscape-design/components/column-layout';
import Link from '@cloudscape-design/components/link';
import Badge from '@cloudscape-design/components/badge';
import ContentLayout from '@cloudscape-design/components/content-layout';

const { baseName, defaultRegion, enabledRegions, version } = __APP_CONFIG__;

const GITHUB_URL = 'https://github.com/amazon-agi-labs/solution-nova-act-qa-studio';

export default function About() {
  return (
    <ContentLayout
      header={<Header variant="h1">About</Header>}
    >
      <SpaceBetween size="l">
        <Container header={<Header variant="h2">QA Studio</Header>}>
          <SpaceBetween size="s">
            <Box variant="p">
              A reference solution for automated web application testing with Amazon Nova Act.
              Define test steps in natural language, run them with Nova Act browser automation,
              and review results with video recordings, screenshots, and logs.
            </Box>
            <Box>
              <Link href={GITHUB_URL} external>View on GitHub</Link>
            </Box>
          </SpaceBetween>
        </Container>

        <Container header={<Header variant="h2">Deployment</Header>}>
          <ColumnLayout columns={2} variant="text-grid">
            <div>
              <Box variant="awsui-key-label">Instance name</Box>
              <Box>{baseName}</Box>
            </div>
            <div>
              <Box variant="awsui-key-label">Version</Box>
              <Box><Badge>{version}</Badge></Box>
            </div>
            <div>
              <Box variant="awsui-key-label">Default region</Box>
              <Box>{defaultRegion}</Box>
            </div>
            <div>
              <Box variant="awsui-key-label">Enabled regions</Box>
              <Box>{enabledRegions.join(', ')}</Box>
            </div>
          </ColumnLayout>
        </Container>
      </SpaceBetween>
    </ContentLayout>
  );
}
