import React from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import Box from "@cloudscape-design/components/box";
import Spinner, {SpinnerProps} from "@cloudscape-design/components/spinner";
import SpaceBetween from "@cloudscape-design/components/space-between";

// Basic loading spinner with text
interface LoadingSpinnerProps {
  size?: 'small' | 'normal' | 'large';
  text?: string;
}

export function LoadingSpinner({ size = 'normal', text = 'Loading...' }: LoadingSpinnerProps) {
  return (
    <Box textAlign="center" padding="s">
      <SpaceBetween direction="vertical" size="s" alignItems="center">
        <Spinner size="normal" />
        <Box variant="p" color="text-body-secondary">
          {text}
        </Box>
      </SpaceBetween>
    </Box>
  );
}

// Loading state for containers with headers
interface ContainerLoadingProps {
  title: string;
  text?: string;
  size?: 'small' | 'normal' | 'large';
}

export function ContainerLoading({ title, text = 'Loading...', }: ContainerLoadingProps) {
  return (
    <Container
      header={<Header variant="h2">{title}</Header>}
    >
      <Box textAlign="center" padding="l">
        <SpaceBetween direction="vertical" size="s" alignItems="center">
          <Spinner size="normal" />
          <Box variant="p" color="text-body-secondary">
            {text}
          </Box>
        </SpaceBetween>
      </Box>
    </Container>
  );
}

// Loading state for headers
interface HeaderLoadingProps {
  variant?: 'h1' | 'h2' | 'h3';
  text?: string;
}

export function HeaderLoading({ variant = 'h1', text = 'Loading...' }: HeaderLoadingProps) {
  return (
    <Header variant={variant}>
      <Spinner size="normal" />
      {text}
    </Header>
  );
}

// Empty state component
interface EmptyStateProps {
  title: string;
  message?: string;
  actionText?: string;
  onAction?: () => void;
}

export function EmptyState({ 
  title, 
  message, 
  actionText, 
  onAction 
}: EmptyStateProps) {
  return (
    <Box textAlign="center" padding="l">
      <SpaceBetween direction="vertical" size="m" alignItems="center">
        <Box variant="h3">
          {title}
        </Box>
        {message && (
          <Box variant="p" color="text-body-secondary">
            {message}
          </Box>
        )}
        {actionText && onAction && (
          <button 
            onClick={onAction}
            style={{
              padding: '8px 16px',
              backgroundColor: '#0073bb',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            {actionText}
          </button>
        )}
      </SpaceBetween>
    </Box>
  );
}