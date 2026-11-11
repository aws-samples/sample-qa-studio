import { VariablesEditor, variablesApi } from '../common/VariablesEditor';

interface UsecaseVariablesProps {
  usecaseId: string;
}

/**
 * Adapter for `/usecase/{id}/variables`. GET returns the effective list
 * (application rows first, each tagged `source`); POST replaces the use case's
 * own list, so the editor only ever posts rows that are not inherited.
 */
export default function UsecaseVariables({ usecaseId }: UsecaseVariablesProps) {
  return <VariablesEditor key={usecaseId} api={variablesApi(`usecase/${usecaseId}/variables`)} />;
}
