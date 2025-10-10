import { useState, useEffect, useCallback } from 'react';
import { api } from '../utils/api';

interface LiveViewRecord {
  pk: string;
  sk: string;
  live_url: string;
  created_at: string;
  expires_at: number;
}

interface UseLiveViewUrlResult {
  liveViewUrl: string | null;
  isLoading: boolean;
  error: string | null;
  isExpired: boolean;
  refresh: () => Promise<void>;
}

export function useLiveViewUrl(
  usecaseId: string, 
  executionId: string,
  autoRefresh: boolean = true
): UseLiveViewUrlResult {
  const [liveViewUrl, setLiveViewUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isExpired, setIsExpired] = useState(false);

  const fetchLiveViewUrl = useCallback(async () => {
    if (!usecaseId || !executionId) {
      setIsLoading(false);
      return;
    }

    try {
      setIsLoading(true);
      setError(null);

      const response = await api.get(`usecase/${usecaseId}/executions/${executionId}/live-view`);
      
      if (response && response.live_url) {
        // Check if expired
        const now = Math.floor(Date.now() / 1000);
        const expired = response.expires_at <= now;
        
        setLiveViewUrl(response.live_url);
        setIsExpired(expired);
        
        if (expired) {
          setError('Live view session has expired');
        }
      } else {
        setLiveViewUrl(null);
        setIsExpired(false);
      }
    } catch (err: any) {
      console.error('Error fetching live view URL:', err);
      
      if (err.response?.status === 404) {
        // No live view found - this is normal for completed executions
        setLiveViewUrl(null);
        setError(null);
      } else {
        setError(err.message || 'Failed to fetch live view URL');
      }
      setLiveViewUrl(null);
      setIsExpired(false);
    } finally {
      setIsLoading(false);
    }
  }, [usecaseId, executionId]);

  // Initial fetch
  useEffect(() => {
    fetchLiveViewUrl();
  }, [fetchLiveViewUrl]);

  // Auto-refresh every 30 seconds if enabled and not expired
  useEffect(() => {
    if (!autoRefresh || isExpired || !liveViewUrl) {
      return;
    }

    const interval = setInterval(() => {
      fetchLiveViewUrl();
    }, 30000); // 30 seconds

    return () => clearInterval(interval);
  }, [autoRefresh, isExpired, liveViewUrl, fetchLiveViewUrl]);

  return {
    liveViewUrl,
    isLoading,
    error,
    isExpired,
    refresh: fetchLiveViewUrl
  };
}