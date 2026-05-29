import { useState } from 'react';
import { api } from '../utils/api';

export interface BatchExecutionResult {
  usecaseId: string;
  usecaseName: string;
  success: boolean;
  error?: string;
}

interface UsecaseRef {
  id: string;
  name: string;
}

export function useBatchExecute() {
  const [executing, setExecuting] = useState(false);
  const [results, setResults] = useState<BatchExecutionResult[] | null>(null);

  async function executeBatch(usecases: UsecaseRef[]): Promise<BatchExecutionResult[]> {
    setExecuting(true);
    setResults(null);

    const promises = usecases.map(async (usecase) => {
      try {
        await api.post(`usecase/${usecase.id}/execute?trigger-type=OnDemandHeadless`, {});
        return { usecaseId: usecase.id, usecaseName: usecase.name, success: true };
      } catch (error) {
        return { usecaseId: usecase.id, usecaseName: usecase.name, success: false, error: (error as Error).message };
      }
    });

    const batchResults = await Promise.all(promises);
    setResults(batchResults);
    setExecuting(false);
    return batchResults;
  }

  const successCount = results?.filter(r => r.success).length ?? 0;
  const failureCount = results?.filter(r => !r.success).length ?? 0;

  return { executeBatch, executing, results, successCount, failureCount };
}
