import React, { Suspense } from 'react';
import { ContainerLoading, LoadingSpinner } from './LoadingStates';

interface LazyWrapperProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
  containerTitle?: string;
  loadingText?: string;
  enablePerformanceMonitoring?: boolean;
}

// Wrapper for lazy-loaded components with loading fallback
export function LazyWrapper({ 
  children, 
  fallback, 
  containerTitle, 
  loadingText = 'Loading component...',
  enablePerformanceMonitoring = false
}: LazyWrapperProps) {
  const defaultFallback = containerTitle ? (
    <ContainerLoading title={containerTitle} text={loadingText} />
  ) : (
    <LoadingSpinner text={loadingText} />
  );

  // Add performance monitoring if enabled
  React.useEffect(() => {
    if (enablePerformanceMonitoring && containerTitle) {
      const startTime = performance.now();
      return () => {
        const endTime = performance.now();
        console.log(`${containerTitle} rendered in ${endTime - startTime}ms`);
      };
    }
  }, [containerTitle, enablePerformanceMonitoring]);

  return (
    <Suspense fallback={fallback || defaultFallback}>
      {children}
    </Suspense>
  );
}

// Higher-order component for creating lazy-loaded components
export function withLazyLoading<T extends object>(
  importFunction: () => Promise<{ default: React.ComponentType<T> }>,
  fallbackTitle?: string,
  fallbackText?: string
) {
  const LazyComponent = React.lazy(importFunction);

  return function LazyLoadedComponent(props: T) {
    return (
      <LazyWrapper 
        containerTitle={fallbackTitle}
        loadingText={fallbackText}
      >
        <LazyComponent {...props} />
      </LazyWrapper>
    );
  };
}

// Preload function for components
export function preloadComponent(importFunction: () => Promise<any>) {
  return importFunction();
}