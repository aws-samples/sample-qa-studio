import { ErrorState, errorManager } from './errorManager';

export interface RetryConfig {
  maxRetries: number;
  baseDelay: number;
  maxDelay: number;
  backoffMultiplier: number;
  retryableErrors: string[];
}

export interface RetryResult<T> {
  success: boolean;
  data?: T;
  error?: ErrorState;
  attempts: number;
}

export class RetryManager {
  private static defaultConfig: RetryConfig = {
    maxRetries: 3,
    baseDelay: 1000,
    maxDelay: 8000,
    backoffMultiplier: 2,
    retryableErrors: ['network', 'bedrock', 'import', 'rate_limit']
  };

  static async executeWithRetry<T>(
    operation: () => Promise<T>,
    config: Partial<RetryConfig> = {}
  ): Promise<RetryResult<T>> {
    const finalConfig = { ...this.defaultConfig, ...config };
    let lastError: ErrorState | null = null;
    let attempts = 0;

    for (let attempt = 0; attempt <= finalConfig.maxRetries; attempt++) {
      attempts = attempt + 1;
      
      try {
        const result = await operation();
        return {
          success: true,
          data: result,
          attempts
        };
      } catch (error) {
        // Convert error to ErrorState if needed
        if (!(error as ErrorState).type) {
          lastError = errorManager.createError('unknown', (error as Error).message);
        } else {
          lastError = error as ErrorState;
        }

        // Update retry count
        lastError = errorManager.incrementRetryCount(lastError);

        // Check if we should retry
        const shouldRetry = attempt < finalConfig.maxRetries && 
                           finalConfig.retryableErrors.includes(lastError.type) &&
                           errorManager.canRetry(lastError);

        if (!shouldRetry) {
          break;
        }

        // Calculate delay with exponential backoff
        const delay = Math.min(
          finalConfig.baseDelay * Math.pow(finalConfig.backoffMultiplier, attempt),
          finalConfig.maxDelay
        );

        // Wait before retrying
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }

    return {
      success: false,
      error: lastError || errorManager.createError('unknown', 'Operation failed'),
      attempts
    };
  }

  static async executeWithCircuitBreaker<T>(
    operation: () => Promise<T>,
    circuitBreakerKey: string,
    config: Partial<RetryConfig> = {}
  ): Promise<RetryResult<T>> {
    const circuitState = this.getCircuitState(circuitBreakerKey);
    
    // Check if circuit is open
    if (circuitState.isOpen && Date.now() - circuitState.lastFailure < circuitState.timeout) {
      return {
        success: false,
        error: errorManager.createError('bedrock', 'Service temporarily unavailable due to repeated failures'),
        attempts: 0
      };
    }

    const result = await this.executeWithRetry(operation, config);

    // Update circuit breaker state
    if (result.success) {
      this.resetCircuit(circuitBreakerKey);
    } else {
      this.recordFailure(circuitBreakerKey);
    }

    return result;
  }

  private static circuitStates = new Map<string, {
    failures: number;
    lastFailure: number;
    isOpen: boolean;
    timeout: number;
  }>();

  private static getCircuitState(key: string) {
    if (!this.circuitStates.has(key)) {
      this.circuitStates.set(key, {
        failures: 0,
        lastFailure: 0,
        isOpen: false,
        timeout: 30000 // 30 seconds
      });
    }
    return this.circuitStates.get(key)!;
  }

  private static recordFailure(key: string) {
    const state = this.getCircuitState(key);
    state.failures++;
    state.lastFailure = Date.now();
    
    // Open circuit after 3 failures
    if (state.failures >= 3) {
      state.isOpen = true;
    }
  }

  private static resetCircuit(key: string) {
    const state = this.getCircuitState(key);
    state.failures = 0;
    state.isOpen = false;
    state.lastFailure = 0;
  }
}

// Hook for React components
export function useRetry() {
  const executeWithRetry = async <T>(
    operation: () => Promise<T>,
    config?: Partial<RetryConfig>
  ): Promise<RetryResult<T>> => {
    return RetryManager.executeWithRetry(operation, config);
  };

  const executeWithCircuitBreaker = async <T>(
    operation: () => Promise<T>,
    circuitBreakerKey: string,
    config?: Partial<RetryConfig>
  ): Promise<RetryResult<T>> => {
    return RetryManager.executeWithCircuitBreaker(operation, circuitBreakerKey, config);
  };

  return {
    executeWithRetry,
    executeWithCircuitBreaker
  };
}