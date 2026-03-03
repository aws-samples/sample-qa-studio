import React, { useEffect } from 'react';

interface PerformanceMonitorProps {
  componentName: string;
  children: React.ReactNode;
  enableLogging?: boolean;
}

// Component to monitor performance of lazy-loaded components
export function PerformanceMonitor({ 
  componentName, 
  children, 
  enableLogging = process.env.NODE_ENV === 'development' 
}: PerformanceMonitorProps) {
  useEffect(() => {
    if (!enableLogging) return;

    const startTime = performance.now();
    
    return () => {
      const endTime = performance.now();
      const renderTime = endTime - startTime;
      
      console.log(`🚀 ${componentName} rendered in ${renderTime.toFixed(2)}ms`);
      
      // Track performance metrics
      if ('performance' in window && 'measure' in performance) {
        try {
          performance.mark(`${componentName}-start`);
          performance.mark(`${componentName}-end`);
          performance.measure(`${componentName}-render`, `${componentName}-start`, `${componentName}-end`);
        } catch (error) {
          // Ignore performance API errors
        }
      }
    };
  }, [componentName, enableLogging]);

  return <>{children}</>;
}

// Hook to measure component load time
export function useLoadTimeTracker(componentName: string) {
  useEffect(() => {
    const startTime = performance.now();
    
    return () => {
      const endTime = performance.now();
      const loadTime = endTime - startTime;
      
      // Send to analytics or logging service
      if (process.env.NODE_ENV === 'development') {
        console.log(`📊 ${componentName} total load time: ${loadTime.toFixed(2)}ms`);
      }
      
      // You could send this to an analytics service
      // analytics.track('component_load_time', {
      //   component: componentName,
      //   loadTime: loadTime,
      //   timestamp: Date.now()
      // });
    };
  }, [componentName]);
}

// Performance observer for monitoring lazy loading
export class LazyLoadingPerformanceObserver {
  private static instance: LazyLoadingPerformanceObserver;
  private observer: PerformanceObserver | null = null;
  private metrics: Map<string, number> = new Map();

  static getInstance(): LazyLoadingPerformanceObserver {
    if (!LazyLoadingPerformanceObserver.instance) {
      LazyLoadingPerformanceObserver.instance = new LazyLoadingPerformanceObserver();
    }
    return LazyLoadingPerformanceObserver.instance;
  }

  startObserving() {
    if (!('PerformanceObserver' in window)) return;

    this.observer = new PerformanceObserver((list) => {
      const entries = list.getEntries();
      entries.forEach((entry) => {
        if (entry.name.includes('chunk') || entry.name.includes('lazy')) {
          this.metrics.set(entry.name, entry.duration);
          console.log(`📦 Lazy chunk loaded: ${entry.name} in ${entry.duration.toFixed(2)}ms`);
        }
      });
    });

    this.observer.observe({ entryTypes: ['measure', 'navigation'] });
  }

  stopObserving() {
    if (this.observer) {
      this.observer.disconnect();
      this.observer = null;
    }
  }

  getMetrics() {
    return new Map(this.metrics);
  }

  clearMetrics() {
    this.metrics.clear();
  }
}

// Hook to initialize performance monitoring
export function usePerformanceMonitoring(enabled: boolean = process.env.NODE_ENV === 'development') {
  useEffect(() => {
    if (!enabled) return;

    const observer = LazyLoadingPerformanceObserver.getInstance();
    observer.startObserving();

    return () => {
      observer.stopObserving();
    };
  }, [enabled]);
}