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

// Inline loading for smaller components
interface InlineLoadingProps {
  text?: string;
  size?: 'small' | 'normal' | 'large';
}

export function InlineLoading({ text = 'Loading...', size = 'normal' }: InlineLoadingProps) {
  return (
    <SpaceBetween direction="horizontal" size="xs" alignItems="center">
      <Spinner size="normal" />
      <Box variant="span" color="text-body-secondary">
        {text}
      </Box>
    </SpaceBetween>
  );
}

// Full page loading
interface PageLoadingProps {
  title?: string;
  text?: string;
}

export function PageLoading({ title = 'Loading', text = 'Please wait while we load your data...' }: PageLoadingProps) {
  return (
    <Box textAlign="center" padding="xxl">
      <SpaceBetween direction="vertical" size="m" alignItems="center">
        <Spinner size="large" />
        <Box variant="h2">{title}</Box>
        <Box variant="p" color="text-body-secondary">
          {text}
        </Box>
      </SpaceBetween>
    </Box>
  );
}

// Loading skeleton for tables/lists
export function TableLoading({ rows = 3 }: { rows?: number }) {
  return (
    <SpaceBetween direction="vertical" size="s">
      {Array.from({ length: rows }, (_, index) => (
        <Box key={index} padding="s">
          <div
            style={{
              height: '20px',
              backgroundColor: '#f1f1f1',
              borderRadius: '4px',
              animation: 'pulse 1.5s ease-in-out infinite'
            }}
          />
        </Box>
      ))}
      <style>{`
        @keyframes pulse {
          0% { opacity: 1; }
          50% { opacity: 0.5; }
          100% { opacity: 1; }
        }
      `}</style>
    </SpaceBetween>
  );
}

// Error state component
interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
}

export function ErrorState({ 
  title = 'Something went wrong', 
  message = 'We encountered an error while loading your data.',
  onRetry 
}: ErrorStateProps) {
  return (
    <Box textAlign="center" padding="l">
      <SpaceBetween direction="vertical" size="m" alignItems="center">
        <Box variant="h3" color="text-status-error">
          {title}
        </Box>
        <Box variant="p" color="text-body-secondary">
          {message}
        </Box>
        {onRetry && (
          <button 
            onClick={onRetry}
            style={{
              padding: '8px 16px',
              backgroundColor: '#0073bb',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            Try Again
          </button>
        )}
      </SpaceBetween>
    </Box>
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