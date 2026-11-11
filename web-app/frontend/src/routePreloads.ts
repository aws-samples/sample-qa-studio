/**
 * Route chunks preloaded once the app is idle, so the first navigation to
 * them does not wait for a download. One list for both the
 * requestIdleCallback path and its setTimeout fallback (App.tsx).
 */
export const ROUTE_PRELOADS: ReadonlyArray<() => Promise<unknown>> = [
  () => import('./components/applications/ApplicationsPage'),
  () => import('./components/dashboard/ApplicationDetailView'),
  () => import('./components/applications/ApplicationVariablesPage'),
  () => import('./components/applications/ApplicationSecretsPage'),
  () => import('./components/applications/ApplicationDatasetsPage'),
  () => import('./components/unified-wizard/UnifiedWizard'),
  () => import('./components/UsecaseDetailRefactored'),
  () => import('./components/execution/ExecutionDetailPanel'),
  () => import('./components/OAuthClients'),
  () => import('./components/CreateOAuthClient'),
  () => import('./components/templates/TemplateLibrary'),
  () => import('./components/templates/TemplateDetail'),
  () => import('./components/TestSuites'),
  () => import('./components/CreateTestSuite'),
  () => import('./components/UpdateTestSuite'),
  () => import('./components/TestSuiteDetail'),
  () => import('./components/AddUsecasesToSuite'),
  () => import('./components/ConfigureSchedule'),
];

/** Fire every preload; failures are ignored (the route loads on demand). */
export function preloadRoutes(): void {
  ROUTE_PRELOADS.forEach((load) => {
    load().catch(() => undefined);
  });
}
