// Bundle optimization utilities

// Lazy load heavy third-party libraries
export const lazyImports = {
  // Lazy load ACE editor only when needed
  aceEditor: () => import('ace-builds'),
  
  // Lazy load code editor component
  codeEditor: () => import('@cloudscape-design/components/code-editor'),
  
  // Lazy load chart libraries if used
  // charts: () => import('recharts'),
  
  // Lazy load date picker if used
  // datePicker: () => import('@cloudscape-design/components/date-picker'),
};

// Preload critical components
export const preloadCriticalComponents = () => {
  // Preload components that are likely to be used soon
  const criticalImports = [
    () => import('../components/UsecaseDetailRefactored'),
    () => import('../components/ExecutionDetail'),
  ];

  return Promise.allSettled(criticalImports.map(importFn => importFn()));
};

// Dynamic import with error handling
export const safeDynamicImport = async <T>(
  importFn: () => Promise<T>,
  fallback?: T
): Promise<T> => {
  try {
    return await importFn();
  } catch (error) {
    console.warn('Failed to dynamically import module:', error);
    if (fallback) {
      return fallback;
    }
    throw error;
  }
};

// Check if a module is already loaded
export const isModuleLoaded = (moduleName: string): boolean => {
  // This is a simplified check - in a real app you might want to track this more precisely
  return document.querySelector(`script[src*="${moduleName}"]`) !== null;
};

// Prefetch resources
export const prefetchResource = (url: string, type: 'script' | 'style' | 'fetch' = 'fetch') => {
  const link = document.createElement('link');
  link.rel = type === 'fetch' ? 'prefetch' : 'preload';
  if (type !== 'fetch') {
    link.as = type;
  }
  link.href = url;
  document.head.appendChild(link);
};

// Performance monitoring for lazy loading
export const measureLoadTime = async <T>(
  name: string,
  importFn: () => Promise<T>
): Promise<T> => {
  const startTime = performance.now();
  try {
    const result = await importFn();
    const endTime = performance.now();
    console.log(`Loaded ${name} in ${endTime - startTime}ms`);
    return result;
  } catch (error) {
    const endTime = performance.now();
    // console.error(`Failed to load ${name} after ${endTime - startTime}ms:`, error);
    throw error;
  }
};