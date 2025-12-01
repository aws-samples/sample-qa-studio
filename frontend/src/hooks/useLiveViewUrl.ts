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
      // Only show loading on first fetch, not on subsequent polls
      if (!liveViewUrl) {
        setIsLoading(true);
      }
      setError(null);

      const response = await api.get(`usecase/${usecaseId}/executions/${executionId}/live-view`);
      
      if (response && response.live_url) {
        // Check if expired
        const now = Math.floor(Date.now() / 1000);
        const expired = response.expires_at <= now;
        
        setLiveViewUrl(response.live_url);
        setIsExpired(expired);
        setIsLoading(false);
        
        if (expired) {
          setError('Live view session has expired');
        }
      } else {
        setLiveViewUrl(null);
        setIsExpired(false);
        // Keep loading state if we haven't found URL yet
      }
    } catch (err: any) {
      console.error('Error fetching live view URL:', err);
      
      if (err.response?.status === 404) {
        // No live view found yet - keep waiting
        setLiveViewUrl(null);
        setError(null);
        // Keep loading state if we haven't found URL yet
      } else {
        // Real error
        setError(err.message || 'Failed to fetch live view URL');
        setLiveViewUrl(null);
        setIsExpired(false);
        setIsLoading(false);
      }
    }
  }, [usecaseId, executionId, liveViewUrl]);

  // Initial fetch
  useEffect(() => {
    fetchLiveViewUrl();
  }, [fetchLiveViewUrl]);

  // Auto-refresh with adaptive polling
  useEffect(() => {
    if (!autoRefresh || isExpired) {
      return;
    }

    // Poll more frequently (2s) when URL is not available yet
    // Poll less frequently (30s) when URL is available to check for expiry
    const pollInterval = !liveViewUrl ? 2000 : 30000;

    const interval = setInterval(() => {
      fetchLiveViewUrl();
    }, pollInterval);

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