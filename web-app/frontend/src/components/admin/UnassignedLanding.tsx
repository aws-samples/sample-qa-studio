import React from 'react';
import Box from '@cloudscape-design/components/box';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Icon from '@cloudscape-design/components/icon';

const UnassignedLanding: React.FC = () => {
  return (
    <Box textAlign="center" padding="xxl">
      <SpaceBetween direction="vertical" size="l">
        <Icon name="status-warning" size="big" variant="warning" />
        <Header variant="h1" data-testid="unassigned-heading">
          No Team Access
        </Header>
        <Box variant="p" color="text-body-secondary" fontSize="heading-m">
          You have not been assigned to a team yet.
        </Box>
        <Box variant="p" color="text-body-secondary">
          Contact your administrator to get access to applications and test cases.
        </Box>
      </SpaceBetween>
    </Box>
  );
};

export default UnassignedLanding;
