import type { CreationMethod, CreationPath, WizardAction } from './types';

/**
 * Deep links into the unified wizard (`/create/new?...`).
 *
 * | Param      | Values                                                   | Effect                                   |
 * |------------|----------------------------------------------------------|------------------------------------------|
 * | `path`     | `create-new`, `clone`, `import`                          | SET_CREATION_PATH, open the next step    |
 * | `method`   | `blank`, `interactive-wizard`, `template`, `user-journey` | SET_CREATION_METHOD (needs `create-new`) |
 * | `sourceId` | use case id                                              | preselect the clone source (needs `clone`) |
 *
 * `applicationId` is handled separately by UnifiedWizard (unchanged).
 *
 * Values are matched against the CreationPath / CreationMethod unions, never
 * passed through. If any deep-link param is unknown or contradicts `path`, the
 * whole deep link is ignored and the wizard starts at "How to start".
 */

const CREATION_PATHS: ReadonlyArray<Exclude<CreationPath, null>> = ['create-new', 'clone', 'import'];
const CREATION_METHODS: ReadonlyArray<Exclude<CreationMethod, null>> = [
  'blank', 'interactive-wizard', 'template', 'user-journey',
];
const SOURCE_ID = /^[A-Za-z0-9_-]{1,128}$/;

/** Index of the first step after "How to start" (every path has one). */
const FIRST_STEP_AFTER_PATH = 1;

function asPath(value: string | null): Exclude<CreationPath, null> | undefined {
  return CREATION_PATHS.find((p) => p === value);
}

function asMethod(value: string | null): Exclude<CreationMethod, null> | undefined {
  return CREATION_METHODS.find((m) => m === value);
}

/**
 * Reducer actions that apply the deep link in `params`, in order; `[]` when
 * there is no (valid) deep link.
 *
 * With a path the wizard opens on the step after "How to start". A `method`
 * is preselected on the "Creation method" step rather than jumped to, because
 * platform selection and basic info still come before it.
 */
export function deepLinkActions(params: URLSearchParams): WizardAction[] {
  const rawPath = params.get('path');
  const rawMethod = params.get('method');
  const rawSource = params.get('sourceId');
  if (rawPath === null) {
    return [];
  }

  const path = asPath(rawPath);
  if (!path) return [];
  if (rawMethod !== null && (path !== 'create-new' || !asMethod(rawMethod))) return [];
  if (rawSource !== null && (path !== 'clone' || !SOURCE_ID.test(rawSource))) return [];

  const actions: WizardAction[] = [{ type: 'SET_CREATION_PATH', payload: path }];
  const method = asMethod(rawMethod);
  if (method) {
    actions.push({ type: 'SET_CREATION_METHOD', payload: method });
  }
  if (rawSource !== null) {
    // Same dispatch SelectSourceStep makes; it then loads the source detail.
    actions.push({
      type: 'UPDATE_CLONE_CONFIG',
      payload: { selectedUsecaseId: rawSource, usecaseDetail: null, newName: '' },
    });
  }
  actions.push({ type: 'SET_ACTIVE_STEP', payload: FIRST_STEP_AFTER_PATH });
  return actions;
}
