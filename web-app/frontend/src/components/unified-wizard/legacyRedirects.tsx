import { Navigate, Route, useLocation } from 'react-router-dom';

/**
 * Old creation URLs → the unified wizard (`/create/new`), so bookmarks and
 * doc links keep working. Each entry maps the old path onto the wizard's
 * deep-link params (deepLink.ts); the old query string is kept (e.g.
 * `/create/clone?sourceId=x` → `/create/new?path=clone&sourceId=x`).
 *
 * `/wizard/:sessionId` lands on the plain wizard: an interactive session
 * cannot be resumed by id (SetupAndRecordStep always starts a new one).
 */
const LEGACY_CREATE_REDIRECTS: ReadonlyArray<{ path: string; params: Record<string, string> }> = [
  { path: '/create', params: {} },
  { path: '/create/blank', params: { path: 'create-new', method: 'blank' } },
  { path: '/create/import', params: { path: 'import' } },
  { path: '/create/template', params: { path: 'create-new', method: 'template' } },
  { path: '/create/clone', params: { path: 'clone' } },
  { path: '/create/journey', params: { path: 'create-new', method: 'user-journey' } },
  { path: '/create/wizard/setup', params: { path: 'create-new', method: 'interactive-wizard' } },
  { path: '/wizard/:sessionId', params: {} },
];

/** The wizard URL for an old creation URL: mapped params first, then the old query. */
export function unifiedWizardUrl(params: Record<string, string>, search: string): string {
  const merged = new URLSearchParams(params);
  new URLSearchParams(search).forEach((value, key) => {
    if (!merged.has(key)) merged.append(key, value);
  });
  const query = merged.toString();
  return query ? `/create/new?${query}` : '/create/new';
}

function LegacyCreateRedirect({ params }: { params: Record<string, string> }) {
  const { search } = useLocation();
  return <Navigate to={unifiedWizardUrl(params, search)} replace />;
}

/** `<Route>` elements for every old creation URL; render them inside `<Routes>`. */
export function legacyCreateRoutes() {
  return LEGACY_CREATE_REDIRECTS.map(({ path, params }) => (
    <Route key={path} path={path} element={<LegacyCreateRedirect params={params} />} />
  ));
}
