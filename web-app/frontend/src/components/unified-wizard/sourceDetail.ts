/**
 * Detail loaders for the wizard's clone and template sources. The record and
 * its steps are required; variables (and a use case's headers) are optional:
 * a failing request for them yields an empty list/map instead of failing the
 * whole load.
 */
import { api } from '../../utils/api';
import type { TemplateDetail, UsecaseDetail } from './types';

function optional<T>(path: string, fallback: T): Promise<T> {
  return api.get(path).catch(() => fallback);
}

export async function fetchUsecaseDetail(usecaseId: string): Promise<UsecaseDetail> {
  const base = `usecase/${usecaseId}`;
  const [usecase, steps, variables, headers] = await Promise.all([
    api.get(base),
    api.get(`${base}/steps`),
    optional(`${base}/variables`, { variables: [] }),
    optional(`${base}/headers`, { headers: {} }),
  ]);
  return {
    ...usecase,
    steps: steps.steps || [],
    variables: variables.variables || [],
    headers: headers.headers || {},
  };
}

export async function fetchTemplateDetail(templateId: string): Promise<TemplateDetail> {
  const base = `templates/${templateId}`;
  const [template, steps, variables] = await Promise.all([
    api.get(base),
    api.get(`${base}/steps`),
    optional(`${base}/variables`, { variables: [] }),
  ]);
  return {
    ...template,
    steps: steps.steps || [],
    variables: variables.variables || [],
  };
}
