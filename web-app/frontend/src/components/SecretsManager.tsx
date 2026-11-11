import { api } from '../utils/api';
import { KeyValueManager, type KeyValueApi, type KeyValueItem, type KeyValueLabels } from './common/KeyValueManager';

interface SecretsManagerProps {
  usecaseId: string;
}

/** Row of `GET usecase/{id}/secrets` / `GET applications/{id}/secrets` (values are never returned). */
export interface SecretListEntry {
  key: string;
  description?: string;
  /** Only on the use-case route: `usecase` or `application` (inherited, unshadowed). */
  source?: string;
}

/**
 * Adapter for the secrets routes. `path` is `usecase/{id}/secrets` or
 * `applications/{id}/secrets`; both share the body shapes (POST `{secrets:
 * [{key, value}]}` creates or updates, DELETE `{secret_key}`). The list keeps
 * keys and `source` only.
 */
export function secretsApi(path: string): KeyValueApi {
  return {
    list: async () => {
      const response = await api.get(path);
      return ((response?.secrets || []) as SecretListEntry[]).map(
        (secret): KeyValueItem => (secret.source ? { key: secret.key, source: secret.source } : { key: secret.key }),
      );
    },
    save: async (drafts) => {
      await api.post(path, { secrets: drafts });
    },
    remove: async (key) => {
      await api.delete(path, { secret_key: key });
    },
  };
}

/**
 * Option for the secret-step dropdowns (StepFormModal, wizard StepForm). The
 * value is always the bare key — the executor resolves the use-case secret
 * first and falls back to the application one — and inherited secrets are
 * marked in the label.
 */
export function secretStepOption(secret: SecretListEntry): { label: string; value: string; description?: string } {
  return {
    label: secret.source === 'application' ? `${secret.key} (application)` : secret.key,
    value: secret.key,
    description: secret.description,
  };
}

const SECRET_LABELS: Omit<KeyValueLabels, 'emptyText' | 'description'> = {
  singular: 'secret',
  plural: 'secrets',
  singularTitle: 'Secret',
  pluralTitle: 'Secrets',
  keyLabel: 'Secret Key',
  valueLabel: 'Secret Value',
  keyPlaceholder: 'e.g., api_key, password, token',
  valuePlaceholder: 'Enter the secret value',
};

const USECASE_SECRET_LABELS: KeyValueLabels = {
  ...SECRET_LABELS,
  description:
    'Manage sensitive data like passwords, API keys, and tokens. Secrets are stored securely in AWS Secrets Manager and can be referenced in your secret steps when designing your workflow. Secrets of the owning application are inherited; add a secret with the same key to override it for this use case.',
  emptyText: 'No secrets configured for this usecase.',
};

export const APPLICATION_SECRET_LABELS: KeyValueLabels = {
  ...SECRET_LABELS,
  description:
    'Secrets every use case of this application can reference in its secret steps. Stored in AWS Secrets Manager; a use case secret with the same key takes precedence.',
  emptyText: 'No secrets configured for this application.',
};

export default function SecretsManager({ usecaseId }: SecretsManagerProps) {
  return (
    <KeyValueManager
      key={usecaseId}
      api={secretsApi(`usecase/${usecaseId}/secrets`)}
      masked
      ownerSource="usecase"
      readOnlyRowLabel="Application"
      labels={USECASE_SECRET_LABELS}
    />
  );
}
