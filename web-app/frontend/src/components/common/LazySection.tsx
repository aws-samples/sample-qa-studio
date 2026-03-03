import React, { useState, useEffect, useRef } from 'react';
import { LazyWrapper } from './LazyWrapper';
import { ContainerLoading } from './LoadingStates';

interface LazySectionProps {
  children: React.ReactNode;
  containerTitle?: string;
  loadingText?: string;
  rootMargin?: string;
  threshold?: number;
}

// Component that only loads when it comes into view
export function LazySection({ 
  children, 
  containerTitle, 
  loadingText = 'Loading...', 
  rootMargin = '100px',
  threshold = 0.1 
}: LazySectionProps) {
  const [isVisible, setIsVisible] = useState(false);
  const [hasLoaded, setHasLoaded] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !hasLoaded) {
          setIsVisible(true);
          setHasLoaded(true);
          observer.disconnect();
        }
      },
      {
        rootMargin,
        threshold
      }
    );

    if (ref.current) {
      observer.observe(ref.current);
    }

    return () => observer.disconnect();
  }, [rootMargin, threshold, hasLoaded]);

  return (
    <div ref={ref}>
      {isVisible ? (
        <LazyWrapper 
          containerTitle={containerTitle}
          loadingText={loadingText}
        >
          {children}
        </LazyWrapper>
      ) : (
        containerTitle ? (
          <ContainerLoading 
            title={containerTitle}
            text="Preparing to load..."
          />
        ) : (
          <div style={{ height: '200px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ color: '#5f6b7a' }}>Loading when visible...</span>
          </div>
        )
      )}
    </div>
  );
}

// Hook for intersection observer
export function useIntersectionObserver(
  callback: (isIntersecting: boolean) => void,
  options: IntersectionObserverInit = {}
) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => callback(entry.isIntersecting),
      options
    );

    if (ref.current) {
      observer.observe(ref.current);
    }

    return () => observer.disconnect();
  }, [callback, options]);

  return ref;
}