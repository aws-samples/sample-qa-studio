import React, { Component, ReactNode } from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import Alert from "@cloudscape-design/components/alert";
import Button from "@cloudscape-design/components/button";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Box from "@cloudscape-design/components/box";

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
  errorInfo?: React.ErrorInfo;
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
    this.setState({ error, errorInfo });
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: undefined, errorInfo: undefined });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <Container header={<Header variant="h2">Something went wrong</Header>}>
          <SpaceBetween direction="vertical" size="l">
            <Alert
              type="error"
              header="Application Error"
              action={
                <Button onClick={this.handleRetry}>
                  Try Again
                </Button>
              }
            >
              <SpaceBetween direction="vertical" size="s">
                <Box>
                  An unexpected error occurred while loading this component.
                  Please try refreshing the page or contact support if the problem persists.
                </Box>
                {process.env.NODE_ENV === 'development' && this.state.error && (
                  <Box variant="small">
                    <strong>Error Details:</strong> {this.state.error.message}
                  </Box>
                )}
              </SpaceBetween>
            </Alert>
          </SpaceBetween>
        </Container>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;