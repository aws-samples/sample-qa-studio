import { useState, useEffect, useCallback } from 'react';

interface UseAsyncDataOptions<T> {
  initialData?: T;
  dependencies?: any[];
  onError?: (error: Error) => void;
  onSuccess?: (data: T) => void;
}

interface UseAsyncDataReturn<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  setData: (data: T) => void;
}

// Custom hook for handling async data fetching with loading states
export function useAsyncData<T>(
  asyncFunction: () => Promise<T>,
  options: UseAsyncDataOptions<T> = {}
): UseAsyncDataReturn<T> {
  const { 
    initialData = null, 
    dependencies = [], 
    onError, 
    onSuccess 
  } = options;

  const [data, setData] = useState<T | null>(initialData);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      
      const result = await asyncFunction();
      setData(result);
      
      if (onSuccess) {
        onSuccess(result);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An error occurred';
      setError(errorMessage);
      
      if (onError) {
        onError(err instanceof Error ? err : new Error(errorMessage));
      }
    } finally {
      setLoading(false);
    }
  }, [asyncFunction, onError, onSuccess]);

  useEffect(() => {
    fetchData();
  }, dependencies);

  const refetch = useCallback(() => {
    return fetchData();
  }, [fetchData]);

  return {
    data,
    loading,
    error,
    refetch,
    setData
  };
}

// Specialized hook for API calls
export function useApiData<T>(
  apiCall: () => Promise<T>,
  dependencies: any[] = []
) {
  return useAsyncData(apiCall, { dependencies });
}

// Hook for multiple async operations
export function useMultipleAsyncData<T extends Record<string, any>>(
  asyncFunctions: { [K in keyof T]: () => Promise<T[K]> },
  dependencies: any[] = []
) {
  const [data, setData] = useState<Partial<T>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAllData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      
      const promises = Object.entries(asyncFunctions).map(async ([key, fn]) => {
        const result = await (fn as () => Promise<any>)();
        return [key, result];
      });
      
      const results = await Promise.all(promises);
      const newData = Object.fromEntries(results) as T;
      setData(newData);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An error occurred';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  }, [asyncFunctions]);

  useEffect(() => {
    fetchAllData();
  }, dependencies);

  const refetch = useCallback(() => {
    return fetchAllData();
  }, [fetchAllData]);

  return {
    data,
    loading,
    error,
    refetch
  };
}