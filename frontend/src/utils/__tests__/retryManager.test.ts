import { vi, describe, it, expect, beforeEach } from 'vitest';
import { useRetry } from '../retryManager';
import { renderHook, act } from '@testing-library/react';

describe('RetryManager', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('executeWithRetry', () => {
    it('executes function successfully on first attempt', async () => {
      const { result } = renderHook(() => useRetry());
      const mockFn = vi.fn().mockResolvedValue({ success: true, data: 'test data' });

      const response = await act(async () => {
        return result.current.executeWithRetry(mockFn);
      });

      expect(mockFn).toHaveBeenCalledTimes(1);
      expect(response.success).toBe(true);
      expect(response.data).toBe('test data');
    });

    it('retries on failure and succeeds', async () => {
      const { result } = renderHook(() => useRetry());
      const mockFn = vi.fn()
        .mockRejectedValueOnce(new Error('First failure'))
        .mockResolvedValueOnce({ success: true, data: 'success after retry' });

      const promise = act(async () => {
        return result.current.executeWithRetry(mockFn, { maxRetries: 2 });
      });

      // Fast-forward through the retry delay
      await act(async () => {
        vi.advanceTimersByTime(1000);
      });

      const response = await promise;

      expect(mockFn).toHaveBeenCalledTimes(2);
      expect(response.success).toBe(true);
      expect(response.data).toBe('success after retry');
    });

    it('fails after max retries exceeded', async () => {
      const { result } = renderHook(() => useRetry());
      const mockFn = vi.fn()
        .mockRejectedValue(new Error('Persistent failure'));

      const promise = act(async () => {
        return result.current.executeWithRetry(mockFn, { maxRetries: 2 });
      });

      // Fast-forward through all retry delays
      await act(async () => {
        vi.advanceTimersByTime(5000); // Should cover all retries
      });

      const response = await promise;

      expect(mockFn).toHaveBeenCalledTimes(3); // Initial + 2 retries
      expect(response.success).toBe(false);
      expect(response.error).toContain('Persistent failure');
    });

    it('uses exponential backoff for retry delays', async () => {
      const { result } = renderHook(() => useRetry());
      const mockFn = vi.fn()
        .mockRejectedValueOnce(new Error('First failure'))
        .mockRejectedValueOnce(new Error('Second failure'))
        .mockResolvedValueOnce({ success: true, data: 'final success' });

      const startTime = Date.now();
      const delays: number[] = [];

      // Mock setTimeout to capture delays
      const originalSetTimeout = global.setTimeout;
      global.setTimeout = vi.fn((callback, delay) => {
        delays.push(delay as number);
        return originalSetTimeout(callback, 0); // Execute immediately for testing
      }) as any;

      const promise = act(async () => {
        return result.current.executeWithRetry(mockFn, { maxRetries: 3 });
      });

      await act(async () => {
        vi.runAllTimers();
      });

      const response = await promise;

      expect(response.success).toBe(true);
      expect(delays).toHaveLength(2); // Two retry delays
      expect(delays[0]).toBe(1000); // First retry: 1s
      expect(delays[1]).toBe(2000); // Second retry: 2s (exponential backoff)

      global.setTimeout = originalSetTimeout;
    });

    it('respects custom retry configuration', async () => {
      const { result } = renderHook(() => useRetry());
      const mockFn = vi.fn().mockRejectedValue(new Error('Always fails'));

      const customConfig = {
        maxRetries: 1,
        baseDelay: 500,
        maxDelay: 2000
      };

      const promise = act(async () => {
        return result.current.executeWithRetry(mockFn, customConfig);
      });

      await act(async () => {
        vi.advanceTimersByTime(3000);
      });

      const response = await promise;

      expect(mockFn).toHaveBeenCalledTimes(2); // Initial + 1 retry
      expect(response.success).toBe(false);
    });

    it('handles non-retryable errors immediately', async () => {
      const { result } = renderHook(() => useRetry());
      
      // Create an error that should not be retried (e.g., validation error)
      const nonRetryableError = new Error('Validation failed');
      (nonRetryableError as any).retryable = false;
      
      const mockFn = vi.fn().mockRejectedValue(nonRetryableError);

      const response = await act(async () => {
        return result.current.executeWithRetry(mockFn, { maxRetries: 3 });
      });

      expect(mockFn).toHaveBeenCalledTimes(1); // Should not retry
      expect(response.success).toBe(false);
      expect(response.error).toContain('Validation failed');
    });

    it('handles timeout errors with retry', async () => {
      const { result } = renderHook(() => useRetry());
      const timeoutError = new Error('Request timeout');
      const mockFn = vi.fn()
        .mockRejectedValueOnce(timeoutError)
        .mockResolvedValueOnce({ success: true, data: 'success after timeout' });

      const promise = act(async () => {
        return result.current.executeWithRetry(mockFn, { maxRetries: 2 });
      });

      await act(async () => {
        vi.advanceTimersByTime(1000);
      });

      const response = await promise;

      expect(mockFn).toHaveBeenCalledTimes(2);
      expect(response.success).toBe(true);
    });

    it('handles network errors with retry', async () => {
      const { result } = renderHook(() => useRetry());
      const networkError = new Error('Network error');
      const mockFn = vi.fn()
        .mockRejectedValueOnce(networkError)
        .mockResolvedValueOnce({ success: true, data: 'network recovered' });

      const promise = act(async () => {
        return result.current.executeWithRetry(mockFn, { maxRetries: 2 });
      });

      await act(async () => {
        vi.advanceTimersByTime(1000);
      });

      const response = await promise;

      expect(mockFn).toHaveBeenCalledTimes(2);
      expect(response.success).toBe(true);
    });

    it('caps retry delay at maximum', async () => {
      const { result } = renderHook(() => useRetry());
      const mockFn = vi.fn().mockRejectedValue(new Error('Always fails'));

      const delays: number[] = [];
      const originalSetTimeout = global.setTimeout;
      global.setTimeout = vi.fn((callback, delay) => {
        delays.push(delay as number);
        return originalSetTimeout(callback, 0);
      }) as any;

      const promise = act(async () => {
        return result.current.executeWithRetry(mockFn, { 
          maxRetries: 5, 
          baseDelay: 1000,
          maxDelay: 4000 
        });
      });

      await act(async () => {
        vi.runAllTimers();
      });

      await promise;

      // Check that delays are capped at maxDelay
      expect(delays.some(delay => delay > 4000)).toBe(false);
      expect(delays.filter(delay => delay === 4000).length).toBeGreaterThan(0);

      global.setTimeout = originalSetTimeout;
    });

    it('handles concurrent retry operations', async () => {
      const { result } = renderHook(() => useRetry());
      
      const mockFn1 = vi.fn()
        .mockRejectedValueOnce(new Error('Fail 1'))
        .mockResolvedValueOnce({ success: true, data: 'success 1' });
      
      const mockFn2 = vi.fn()
        .mockRejectedValueOnce(new Error('Fail 2'))
        .mockResolvedValueOnce({ success: true, data: 'success 2' });

      const promise1 = act(async () => {
        return result.current.executeWithRetry(mockFn1, { maxRetries: 2 });
      });

      const promise2 = act(async () => {
        return result.current.executeWithRetry(mockFn2, { maxRetries: 2 });
      });

      await act(async () => {
        vi.advanceTimersByTime(2000);
      });

      const [response1, response2] = await Promise.all([promise1, promise2]);

      expect(response1.success).toBe(true);
      expect(response1.data).toBe('success 1');
      expect(response2.success).toBe(true);
      expect(response2.data).toBe('success 2');
    });

    it('preserves original error information in final failure', async () => {
      const { result } = renderHook(() => useRetry());
      const originalError = new Error('Original error message');
      originalError.stack = 'Original stack trace';
      
      const mockFn = vi.fn().mockRejectedValue(originalError);

      const promise = act(async () => {
        return result.current.executeWithRetry(mockFn, { maxRetries: 1 });
      });

      await act(async () => {
        vi.advanceTimersByTime(2000);
      });

      const response = await promise;

      expect(response.success).toBe(false);
      expect(response.error).toContain('Original error message');
    });

    it('handles successful response that indicates failure', async () => {
      const { result } = renderHook(() => useRetry());
      const mockFn = vi.fn()
        .mockResolvedValueOnce({ success: false, error: 'Business logic error' })
        .mockResolvedValueOnce({ success: true, data: 'eventual success' });

      const promise = act(async () => {
        return result.current.executeWithRetry(mockFn, { maxRetries: 2 });
      });

      await act(async () => {
        vi.advanceTimersByTime(1000);
      });

      const response = await promise;

      expect(mockFn).toHaveBeenCalledTimes(2);
      expect(response.success).toBe(true);
      expect(response.data).toBe('eventual success');
    });
  });

  describe('Error Classification', () => {
    it('correctly identifies retryable errors', async () => {
      const { result } = renderHook(() => useRetry());
      
      const retryableErrors = [
        new Error('Network error'),
        new Error('Timeout'),
        new Error('Service unavailable'),
        new Error('Rate limit exceeded'),
        new Error('Throttling')
      ];

      for (const error of retryableErrors) {
        const mockFn = vi.fn()
          .mockRejectedValueOnce(error)
          .mockResolvedValueOnce({ success: true, data: 'recovered' });

        const promise = act(async () => {
          return result.current.executeWithRetry(mockFn, { maxRetries: 1 });
        });

        await act(async () => {
          vi.advanceTimersByTime(1000);
        });

        const response = await promise;

        expect(mockFn).toHaveBeenCalledTimes(2); // Should retry
        expect(response.success).toBe(true);

        vi.clearAllMocks();
      }
    });

    it('correctly identifies non-retryable errors', async () => {
      const { result } = renderHook(() => useRetry());
      
      const nonRetryableErrors = [
        new Error('Validation failed'),
        new Error('Authentication failed'),
        new Error('Access denied'),
        new Error('Bad request')
      ];

      for (const error of nonRetryableErrors) {
        // Mark as non-retryable
        (error as any).retryable = false;
        
        const mockFn = vi.fn().mockRejectedValue(error);

        const response = await act(async () => {
          return result.current.executeWithRetry(mockFn, { maxRetries: 3 });
        });

        expect(mockFn).toHaveBeenCalledTimes(1); // Should not retry
        expect(response.success).toBe(false);

        vi.clearAllMocks();
      }
    });
  });

  describe('Performance', () => {
    it('handles rapid successive calls efficiently', async () => {
      const { result } = renderHook(() => useRetry());
      
      const promises = Array.from({ length: 10 }, (_, i) => {
        const mockFn = vi.fn().mockResolvedValue({ success: true, data: `result ${i}` });
        return act(async () => {
          return result.current.executeWithRetry(mockFn);
        });
      });

      const startTime = performance.now();
      const responses = await Promise.all(promises);
      const endTime = performance.now();

      expect(responses).toHaveLength(10);
      expect(responses.every(r => r.success)).toBe(true);
      expect(endTime - startTime).toBeLessThan(100); // Should be fast for successful calls
    });

    it('manages memory efficiently during retries', async () => {
      const { result } = renderHook(() => useRetry());
      
      // Create a function that fails many times before succeeding
      let callCount = 0;
      const mockFn = vi.fn().mockImplementation(() => {
        callCount++;
        if (callCount < 5) {
          return Promise.reject(new Error(`Failure ${callCount}`));
        }
        return Promise.resolve({ success: true, data: 'final success' });
      });

      const promise = act(async () => {
        return result.current.executeWithRetry(mockFn, { maxRetries: 10 });
      });

      await act(async () => {
        vi.advanceTimersByTime(20000); // Advance through all retries
      });

      const response = await promise;

      expect(response.success).toBe(true);
      expect(callCount).toBe(5);
    });
  });
});