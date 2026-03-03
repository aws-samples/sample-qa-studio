import React, { Suspense } from 'react';
import { LoadingSpinner, ContainerLoading } from './LoadingStates';

interface LazyComponentProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
  containerTitle?: string;
  loadingText?: string;
}

// Simple lazy loading wrapper
export function LazyComponent({ 
  children, 
  fallback, 
  containerTitle, 
  loadingText = 'Loading...' 
}: LazyComponentProps) {
  const defaultFallback = containerTitle ? (
    <ContainerLoading title={containerTitle} text={loadingText} />
  ) : (
    <LoadingSpinner text={loadingText} />
  );

  return (
    <Suspense fallback={fallback || defaultFallback}>
      {children}
    </Suspense>
  );
}

// Simple preloader utility
export const preloadComponent = (importFunction: () => Promise<any>) => {
  return importFunction();
};

// Preload on idle
export const preloadOnIdle = (importFunctions: Array<() => Promise<any>>) => {
  if ('requestIdleCallback' in window) {
    (window as any).requestIdleCallback(() => {
      importFunctions.forEach(fn => fn().catch(() => {}));
    });
  } else {
    setTimeout(() => {
      importFunctions.forEach(fn => fn().catch(() => {}));
    }, 2000);
  }
};