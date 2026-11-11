/**
 * Batch delete of use cases, shared by the Use Cases page and the application
 * detail page so both send the same requests and show the same wording.
 *
 * Authorization is server-side only (`DELETE usecase/{id}` needs
 * `api/usecases.write` and full access); a 403 comes back as a failed item.
 */
import { useState } from 'react';
import type { FlashbarProps } from '@cloudscape-design/components/flashbar';
import { api } from '../utils/api';
import { batchedPromiseAll } from '../utils/batchedPromiseAll';
import type { BatchExecutionResult } from './useBatchExecute';
import type { DeleteNoun } from '../components/common/DeleteConfirmModal';

interface UsecaseRef {
  id: string;
  name: string;
}

export const USECASE_DELETE_NOUN: DeleteNoun = { singular: 'use case', plural: 'use cases', title: 'Use Cases' };

export const USECASE_DELETE_CONSEQUENCES =
  'This will remove all associated data including steps, executions, and configurations.';

/** Flash shown while the batch runs. */
export function deleteInProgressFlash(count: number): FlashbarProps.MessageDefinition {
  return { type: 'info', content: `Deleting ${count} use case(s)...`, loading: true };
}

/** Flashes summarising a finished batch: a success item and/or an error item naming the failed use cases. */
export function deleteResultFlashes(
  results: BatchExecutionResult[],
  onDismiss: () => void,
): FlashbarProps.MessageDefinition[] {
  const succeeded = results.filter((r) => r.success);
  const failed = results.filter((r) => !r.success);
  const items: FlashbarProps.MessageDefinition[] = [];

  if (succeeded.length > 0) {
    items.push({
      type: 'success',
      content: `Successfully deleted ${succeeded.length} use case(s)`,
      dismissible: true,
      onDismiss,
    });
  }
  if (failed.length > 0) {
    items.push({
      type: 'error',
      content: `Failed to delete ${failed.length} use case(s): ${failed.map((r) => r.usecaseName).join(', ')}`,
      dismissible: true,
      onDismiss,
    });
  }
  return items;
}

export function useBatchDelete() {
  const [deleting, setDeleting] = useState(false);

  async function deleteBatch(usecases: UsecaseRef[]): Promise<BatchExecutionResult[]> {
    setDeleting(true);
    try {
      // Batches match the Lambda concurrency limit (batchedPromiseAll default).
      return (await batchedPromiseAll(usecases, async (usecase): Promise<BatchExecutionResult> => {
        try {
          await api.delete(`usecase/${usecase.id}`);
          return { usecaseId: usecase.id, usecaseName: usecase.name, success: true };
        } catch (error) {
          return {
            usecaseId: usecase.id,
            usecaseName: usecase.name,
            success: false,
            error: (error as Error).message,
          };
        }
      })) as BatchExecutionResult[];
    } finally {
      setDeleting(false);
    }
  }

  return { deleteBatch, deleting };
}
