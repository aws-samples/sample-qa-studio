import React, { useEffect, useState, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { Amplify } from 'aws-amplify';
import { Authenticator } from '@aws-amplify/ui-react';
import '@aws-amplify/ui-react/styles.css';
import amplifyconfig from './amplifyconfiguration.json';
import './App.css';
import "@cloudscape-design/global-styles/index.css";
import AppLayout from "@cloudscape-design/components/app-layout";
import SideNavigation from "@cloudscape-design/components/side-navigation";
import TopNavigation from "@cloudscape-design/components/top-navigation";
import Spinner from "@cloudscape-design/components/spinner";
import Box from "@cloudscape-design/components/box";
import { PermissionsProvider, usePermissions } from './auth';
import { SplitPanelProvider, useSplitPanelLayoutProps } from './components/common/splitPanel';
import { api } from './utils/api';
import { legacyCreateRoutes } from './components/unified-wizard/legacyRedirects';
import ExecutionRedirect from './components/ExecutionRedirect';
import { preloadRoutes } from './routePreloads';
import { applicationNavGroup } from './components/applications/applicationNav';

// Configuration loaded from lib/config.ts at build time via Vite

// Lazy load components for code splitting
const HomeScreen = React.lazy(() => import('./components/HomeScreen'));
const UsecaseDetail = React.lazy(() => import('./components/UsecaseDetailRefactored'));
const OAuthClients = React.lazy(() => import('./components/OAuthClients'));
const CreateOAuthClient = React.lazy(() => import('./components/CreateOAuthClient'));
const TemplateLibrary = React.lazy(() => import('./components/templates/TemplateLibrary'));
const TemplateDetail = React.lazy(() => import('./components/templates/TemplateDetail'));
const TestSuites = React.lazy(() => import('./components/TestSuites'));
const CreateTestSuite = React.lazy(() => import('./components/CreateTestSuite'));
const UpdateTestSuite = React.lazy(() => import('./components/UpdateTestSuite'));
const TestSuiteDetail = React.lazy(() => import('./components/TestSuiteDetail'));
const AddUsecasesToSuite = React.lazy(() => import('./components/AddUsecasesToSuite'));
const ConfigureSchedule = React.lazy(() => import('./components/ConfigureSchedule'));
const SuiteExecutionDetail = React.lazy(() => import('./components/SuiteExecutionDetail'));
const UnifiedWizard = React.lazy(() => import('./components/unified-wizard/UnifiedWizard'));
const About = React.lazy(() => import('./components/About'));
const ApplicationsPage = React.lazy(() => import('./components/applications/ApplicationsPage'));
const ApplicationDetailView = React.lazy(() => import('./components/dashboard/ApplicationDetailView'));
const AddUsecasesToApplication = React.lazy(() => import('./components/AddUsecasesToApplication'));
const AddTestSuitesToApplication = React.lazy(() => import('./components/AddTestSuitesToApplication'));
const EditApplication = React.lazy(() => import('./components/EditApplication'));
const ApplicationVariablesPage = React.lazy(() => import('./components/applications/ApplicationVariablesPage'));
const ApplicationSecretsPage = React.lazy(() => import('./components/applications/ApplicationSecretsPage'));
const ApplicationDatasetsPage = React.lazy(() => import('./components/applications/ApplicationDatasetsPage'));

// Admin/Permissions pages
const TeamsListPage = React.lazy(() => import('./components/admin/TeamsListPage'));
const TeamDetailPage = React.lazy(() => import('./components/admin/TeamDetailPage'));
const UsersListPage = React.lazy(() => import('./components/admin/UsersListPage'));
const MyTeamPage = React.lazy(() => import('./components/admin/MyTeamPage'));
const UnassignedLanding = React.lazy(() => import('./components/admin/UnassignedLanding'));

Amplify.configure(amplifyconfig);

/**
 * Memoised on purpose: `AppContent` re-renders whenever a page registers a split panel
 * (`useSplitPanelLayoutProps`). If that re-render reached the pages, a page handing in a
 * fresh `<SplitPanel>` element on every render would re-register in a loop. With no
 * props, this component only re-renders on router changes.
 */
const RoutedContent = React.memo(function RoutedContent() {
  return (
    <Suspense fallback={
      <Box textAlign="center" padding="xxl">
        <Spinner size="large" />
      </Box>
    }>
      <Routes>
        <Route path="/" element={<Navigate to="/applications" replace />} />
        <Route path="/applications" element={<ApplicationsPage />} />
        <Route path="/applications/:id" element={<ApplicationDetailView />} />
        <Route path="/applications/:id/add-usecases" element={<AddUsecasesToApplication />} />
        <Route path="/applications/:id/add-test-suites" element={<AddTestSuitesToApplication />} />
        <Route path="/applications/:id/edit" element={<EditApplication />} />
        <Route path="/applications/:id/variables" element={<ApplicationVariablesPage />} />
        <Route path="/applications/:id/secrets" element={<ApplicationSecretsPage />} />
        <Route path="/applications/:id/datasets" element={<ApplicationDatasetsPage />} />
        <Route path="/usecases" element={<HomeScreen />} />
        <Route path="/create/new" element={<UnifiedWizard />} />
        {/* Old creation URLs redirect into the unified wizard (W2). */}
        {legacyCreateRoutes()}
        <Route path="/templates" element={<TemplateLibrary />} />
        <Route path="/templates/:id" element={<TemplateDetail />} />
        <Route path="/admin/teams" element={<TeamsListPage />} />
        <Route path="/admin/teams/:id" element={<TeamDetailPage />} />
        <Route path="/admin/users" element={<UsersListPage />} />
        <Route path="/my-team" element={<MyTeamPage />} />
        <Route path="/unassigned" element={<UnassignedLanding />} />
        <Route path="/oauth-clients" element={<OAuthClients />} />
        <Route path="/oauth-clients/create" element={<CreateOAuthClient />} />
        <Route path="/test-suites" element={<TestSuites />} />
        <Route path="/test-suites/create" element={<CreateTestSuite />} />
        <Route path="/test-suites/:id" element={<TestSuiteDetail />} />
        <Route path="/test-suites/:id/edit" element={<UpdateTestSuite />} />
        <Route path="/test-suites/:id/add-usecases" element={<AddUsecasesToSuite />} />
        <Route path="/test-suites/:id/schedule" element={<ConfigureSchedule />} />
        <Route path="/test-suites/:suiteId/executions/:executionId" element={<SuiteExecutionDetail />} />
        <Route path="/usecase/:id" element={<UsecaseDetail />} />
        {/* The standalone execution page is gone; its URL opens the panel on the use case page. */}
        <Route path="/usecase/:usecaseId/execution/:executionId" element={<ExecutionRedirect />} />
        <Route path="/about" element={<About />} />
      </Routes>
    </Suspense>
  );
});

function AppContent() {
  const navigate = useNavigate();
  const location = useLocation();
  const [activeHref, setActiveHref] = useState(location.pathname);
  const { hasScope, isAdmin, isTeamLead, teams } = usePermissions();
  const [myTeamName, setMyTeamName] = useState('');
  const splitPanelProps = useSplitPanelLayoutProps();

  useEffect(() => {
    if (isTeamLead && !isAdmin && teams.length > 0) {
      api.get(`teams/${encodeURIComponent(teams[0].team_id)}`)
        .then((data: any) => setMyTeamName(data.name || ''))
        .catch(() => {});
    }
  }, [isTeamLead, isAdmin, teams]);

  // Build navigation items based on user permissions and the current route
  const navigationItems = React.useMemo(() => {
    const items: any[] = [
      // Lists Variables / Secrets / Datasets while an application route is open.
      applicationNavGroup(location.pathname),
      ...(isAdmin ? [
        { type: "link", text: "Use cases", href: "/usecases" },
        { type: "link", text: "Test Suites", href: "/test-suites" },
      ] : []),
      { type: "link", text: "Templates", href: "/templates" },
    ];

    // Team section — visible to team leads (non-admin) for "My Team"
    if (isTeamLead && !isAdmin) {
      items.push({ type: "divider" });
      items.push({ type: "link", text: myTeamName ? `My Team: ${myTeamName}` : "My Team", href: "/my-team" });
    }

    // Admin section — visible to admins
    if (isAdmin) {
      items.push({ type: "divider" });
      items.push({ type: "link", text: "Teams", href: "/admin/teams" });
      items.push({ type: "link", text: "Users", href: "/admin/users" });
    }

    // OAuth section — visible to admins and users with OAuth client access
    const hasOAuthAccess = hasScope('api/oauth-clients.read') || hasScope('api/oauth-clients.write');
    if (hasOAuthAccess || isAdmin) {
      if (!isAdmin) {
        items.push({ type: "divider" });
      }
      items.push({ type: "link", text: "OAuth Clients", href: "/oauth-clients" });
    }

    items.push({ type: "divider" });
    items.push({ type: "link", text: "About", href: "/about" });

    return items;
  }, [hasScope, isAdmin, isTeamLead, myTeamName, location.pathname]);

  // Preload route chunks when the app becomes idle (one list: routePreloads.ts)
  React.useEffect(() => {
    if ('requestIdleCallback' in window) {
      (window as any).requestIdleCallback(preloadRoutes);
    } else {
      setTimeout(preloadRoutes, 2000);
    }
  }, []);

  useEffect(() => {
    setActiveHref(location.pathname);
  }, [location.pathname]);

  return (
    <AppLayout
      navigation={
        <div data-testid="nav-sidebar">
          {(isTeamLead || isAdmin) && <span data-testid="nav-team-section" aria-hidden="true" />}
          {isAdmin && <span data-testid="nav-admin-section" aria-hidden="true" />}
          <SideNavigation
            activeHref={activeHref}
            items={navigationItems}
            onFollow={(event) => {
              if (!event.detail.external) {
                event.preventDefault();
                navigate(event.detail.href);
              }
            }}
          />
        </div>
      }
      toolsHide
      content={<RoutedContent />}
      {...splitPanelProps}
    />
  );
}

function App() {
  useEffect(() => {
    document.body.classList.add('awsui-dark-mode');
  }, []);

  return (
    <Authenticator>
      {({ signOut, user }) => (
        <Router>
          <PermissionsProvider>
            <TopNavigation
              identity={{
                href: "/",
                title: "QA Studio",
              }}
              utilities={[
                {
                  type: "button",
                  text: "Sign out",
                  onClick: signOut
                }
              ]}
            />
            <SplitPanelProvider>
              <AppContent />
            </SplitPanelProvider>
          </PermissionsProvider>
        </Router>
      )}
    </Authenticator>
  );
}

export default App;
