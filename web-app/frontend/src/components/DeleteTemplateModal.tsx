import { useEffect, useState } from 'react';
import Box from "@cloudscape-design/components/box";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Spinner from "@cloudscape-design/components/spinner";
import { api } from '../utils/api';
import { batchedPromiseAll } from '../utils/batchedPromiseAll';
import { TypedDeleteModal } from './common/DeleteConfirmModal';

interface TemplateRef {
  id: string;
  name: string;
}

interface TemplateUsage {
  usecase_id: string;
  name: string;
}

interface TemplateUsages {
  template: TemplateRef;
  usages: TemplateUsage[];
}

interface DeleteTemplateModalProps {
  visible: boolean;
  templateName: string;
  /** Templates about to be deleted; their usages (tests that inserted them) are shown. */
  templates?: TemplateRef[];
  onDismiss: () => void;
  onConfirm: () => void;
  deleting?: boolean;
}

function usageSentence({ template, usages }: TemplateUsages): string {
  if (usages.length === 0) {
    return `"${template.name}" is not used by any test.`;
  }
  const noun = usages.length === 1 ? 'test' : 'tests';
  return `"${template.name}" is used by ${usages.length} ${noun}: ${usages.map((u) => u.name).join(', ')}`;
}

export default function DeleteTemplateModal({
  visible,
  templateName,
  templates = [],
  onDismiss,
  onConfirm,
  deleting = false
}: DeleteTemplateModalProps) {
  const [usages, setUsages] = useState<TemplateUsages[] | null>(null);
  const [loadingUsages, setLoadingUsages] = useState(false);
  // Stable key so the effect re-runs only when the selection changes.
  const templateKey = templates.map((t) => t.id).join(',');

  useEffect(() => {
    if (!visible || templates.length === 0) {
      setUsages(null);
      return;
    }
    let cancelled = false;
    setLoadingUsages(true);
    setUsages(null);
    batchedPromiseAll(templates, async (template) => {
      const data = await api.get(`templates/${template.id}/usages`);
      return { template, usages: (data?.usages ?? []) as TemplateUsage[] };
    })
      .then((loaded) => {
        if (!cancelled) setUsages(loaded as TemplateUsages[]);
      })
      .catch((error) => {
        // Usage info is advisory: never block the deletion on it.
        console.error('Failed to load template usages:', error);
        if (!cancelled) setUsages(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingUsages(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, templateKey]);

  const anyUsage = (usages ?? []).some((u) => u.usages.length > 0);

  return (
    <TypedDeleteModal
      visible={visible}
      header="Delete Template"
      warning={
        <>
          You are about to permanently delete the template <strong>{templateName}</strong>. 
          This will remove all associated steps and variables.
        </>
      }
      onConfirm={onConfirm}
      onDismiss={onDismiss}
      loading={deleting}
    >
      {loadingUsages && (
        <Box>
          <Spinner size="normal" /> Checking which tests use {templates.length === 1 ? 'this template' : 'these templates'}…
        </Box>
      )}

      {!loadingUsages && usages && (
        <Box>
          <SpaceBetween size="xxs">
            {usages.map((entry) => (
              <Box key={entry.template.id} variant="p">{usageSentence(entry)}</Box>
            ))}
            {anyUsage && (
              <Box variant="p" color="text-body-secondary">
                Steps in those tests are kept; the template link is removed.
              </Box>
            )}
          </SpaceBetween>
        </Box>
      )}
    </TypedDeleteModal>
  );
}
