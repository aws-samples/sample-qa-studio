import React from 'react';
import { ContainerLoading, ErrorState } from './LoadingStates';

interface WithLoadingProps {
  loading: boolean;
  error?: string | null;
  loadingText?: string;
  loadingTitle?: string;
  onRetry?: () => void;
}

// Higher-order component for handling loading states
export function withLoading<T extends object>(
  WrappedComponent: React.ComponentType<T>,
  defaultLoadingTitle: string,
  defaultLoadingText?: string
) {
  return function WithLoadingComponent(props: T & WithLoadingProps) {
    const { 
      loading, 
      error, 
      loadingText = defaultLoadingText || 'Loading...', 
      loadingTitle = defaultLoadingTitle,
      onRetry,
      ...restProps 
    } = props;

    if (loading) {
      return (
        <ContainerLoading 
          title={loadingTitle}
          text={loadingText}
        />
      );
    }

    if (error) {
      return (
        <ErrorState 
          title="Failed to load data"
          message={error}
          onRetry={onRetry}
        />
      );
    }

    return <WrappedComponent {...(restProps as T)} />;
  };
}

// Hook for managing loading states
export function useLoadingState(initialLoading = false) {
  const [loading, setLoading] = React.useState(initialLoading);
  const [error, setError] = React.useState<string | null>(null);

  const startLoading = () => {
    setLoading(true);
    setError(null);
  };

  const stopLoading = () => {
    setLoading(false);
  };

  const setErrorState = (errorMessage: string) => {
    setLoading(false);
    setError(errorMessage);
  };

  const reset = () => {
    setLoading(false);
    setError(null);
  };

  return {
    loading,
    error,
    startLoading,
    stopLoading,
    setErrorState,
    reset
  };
}