import { api } from '../utils/api';
import { KeyValueManager, type KeyValueApi, type KeyValueItem } from './common/KeyValueManager';

interface HeadersManagerProps {
  usecaseId: string;
}

function toMap(items: KeyValueItem[]): Record<string, string> {
  return Object.fromEntries(items.map((item) => [item.key, item.value ?? '']));
}

/**
 * Adapter for `/usecase/{id}/headers`. POST replaces the whole header map, so
 * save merges the new rows into the current map and delete posts the map
 * without the removed key.
 */
export function headersApi(usecaseId: string): KeyValueApi {
  const path = `usecase/${usecaseId}/headers`;
  return {
    list: async () => {
      const response = await api.get(path);
      return Object.entries((response?.headers || {}) as Record<string, string>).map(([key, value]) => ({ key, value }));
    },
    save: async (drafts, existing) => {
      const headers = toMap(existing);
      drafts.forEach((d) => {
        headers[d.key.trim()] = d.value.trim();
      });
      await api.post(path, { headers });
    },
    remove: async (key, existing) => {
      const headers = toMap(existing);
      delete headers[key];
      await api.post(path, { headers });
    },
  };
}

export default function HeadersManager({ usecaseId }: HeadersManagerProps) {
  return (
    <KeyValueManager
      key={usecaseId}
      api={headersApi(usecaseId)}
      masked={false}
      labels={{
        singular: 'header',
        plural: 'headers',
        singularTitle: 'Header',
        pluralTitle: 'Headers',
        description:
          'Manage custom HTTP headers that will be sent with every request during workflow execution. Headers are stored in DynamoDB and applied before navigating to the starting URL.',
        keyLabel: 'Header Name',
        valueLabel: 'Header Value',
        keyPlaceholder: 'e.g., Authorization, X-Custom-Header',
        valuePlaceholder: 'Enter the header value',
        emptyText: 'No headers configured for this usecase.',
      }}
    />
  );
}
