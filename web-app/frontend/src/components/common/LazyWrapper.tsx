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

