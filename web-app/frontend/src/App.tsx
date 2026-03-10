import React, { useEffect, useState, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, useNavigate, useLocation } from 'react-router-dom';
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
import ErrorBoundary from './components/ErrorBoundary';

// Configuration loaded from lib/config.ts at build time via Vite

// Lazy load components for code splitting
const HomeScreen = React.lazy(() => import('./components/HomeScreen'));
const CreateUsecaseWizard = React.lazy(() => import('./components/CreateUsecaseWizard'));
const CreateUsecase = React.lazy(() => import('./components/CreateUsecase'));
const ImportUsecase = React.lazy(() => import('./components/ImportUsecase'));
const CloneUsecase = React.lazy(() => import('./components/CloneUsecase'));
const CreateFromTemplate = React.lazy(() => import('./components/CreateFromTemplate'));
const TemplateUsecase = React.lazy(() => import('./components/TemplateUsecase'));
const UserJourneyWizard = React.lazy(() => import('./components/UserJourneyWizard'));
const WizardSetup = React.lazy(() => import('./components/wizard/WizardSetup'));
const InteractiveWizard = React.lazy(() => import('./components/wizard/InteractiveWizard'));
const UsecaseDetail = React.lazy(() => import('./components/UsecaseDetailRefactored'));
const ExecutionDetail = React.lazy(() => import('./components/ExecutionDetailRefactored'));
const Users = React.lazy(() => import('./components/Users'));
const CreateUser = React.lazy(() => import('./components/CreateUser'));
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
const About = React.lazy(() => import('./components/About'));

Amplify.configure(amplifyconfig);



function Usecases() {
  return (
    <div>
      <h1>Use cases</h1>
      <p>This is the usecases page.</p>
    </div>
  );
}

function AppContent() {
  const navigate = useNavigate();
  const location = useLocation();
  const [activeHref, setActiveHref] = useState(location.pathname);
  const [userScopes, setUserScopes] = useState<string[]>([]);

  // Extract scopes from user token
  useEffect(() => {
    const extractScopes = async () => {
      try {
        const { fetchAuthSession } = await import('aws-amplify/auth');
        const session = await fetchAuthSession();
        
        if (session.tokens?.idToken) {
          const idTokenString = session.tokens.idToken.toString();
          const payload = JSON.parse(atob(idTokenString.split('.')[1]));
          const scope = payload.scope || '';
          const scopes = scope.split(' ').filter((s: string) => s.length > 0);
          setUserScopes(scopes);
        }
      } catch (error) {
        console.error('Failed to extract scopes:', error);
        setUserScopes([]);
      }
    };
    
    extractScopes();
  }, []);

  // Check if user has required scope (with admin inheritance)
  const hasScope = (requiredScope: string): boolean => {
    return userScopes.includes('api/admin') || userScopes.includes(requiredScope);
  };

  // Build navigation items based on user scopes
  const navigationItems = React.useMemo(() => {
    const items: any[] = [
      { type: "link", text: "Use cases", href: "/" },
      { type: "link", text: "Test Suites", href: "/test-suites" },
      { type: "link", text: "Templates", href: "/templates" },
    ];

    // Add admin section if user has admin or oauth-clients scopes
    const hasAdminAccess = hasScope('api/admin');
    const hasOAuthAccess = hasScope('api/oauth-clients.read') || hasScope('api/oauth-clients.write');

    if (hasAdminAccess || hasOAuthAccess) {
      items.push({ type: "divider" });
      
      if (hasAdminAccess) {
        items.push({ type: "link", text: "Users", href: "/users" });
      }
      
      if (hasOAuthAccess || hasAdminAccess) {
        items.push({ type: "link", text: "OAuth Clients", href: "/oauth-clients" });
      }
    }

    items.push({ type: "divider" });
    items.push({ type: "link", text: "About", href: "/about" });

    return items;
  }, [userScopes]);

  // Preload components when the app becomes idle
  React.useEffect(() => {
    // Simple idle preloading
    if ('requestIdleCallback' in window) {
      (window as any).requestIdleCallback(() => {
        import('./components/CreateUsecaseWizard');
        import('./components/CreateUsecase');
        import('./components/CreateFromTemplate');
        import('./components/CloneUsecase');
        import('./components/TemplateUsecase');
        import('./components/UserJourneyWizard');
        import('./components/wizard/WizardSetup');
        import('./components/wizard/InteractiveWizard');
        import('./components/UsecaseDetailRefactored');
        import('./components/ExecutionDetailRefactored');
        import('./components/Users');
        import('./components/OAuthClients');
        import('./components/CreateOAuthClient');
        import('./components/templates/TemplateLibrary');
        import('./components/templates/TemplateDetail');
        import('./components/TestSuites');
        import('./components/CreateTestSuite');
        import('./components/UpdateTestSuite');
        import('./components/TestSuiteDetail');
        import('./components/AddUsecasesToSuite');
        import('./components/ConfigureSchedule');
      });
    } else {
      setTimeout(() => {
        import('./components/CreateUsecaseWizard');
        import('./components/CreateUsecase');
        import('./components/CreateFromTemplate');
        import('./components/CloneUsecase');
        import('./components/TemplateUsecase');
        import('./components/UserJourneyWizard');
        import('./components/wizard/WizardSetup');
        import('./components/wizard/InteractiveWizard');
        import('./components/UsecaseDetailRefactored');
        import('./components/ExecutionDetailRefactored');
        import('./components/Users');
        import('./components/OAuthClients');
        import('./components/CreateOAuthClient');
        import('./components/templates/TemplateLibrary');
        import('./components/templates/TemplateDetail');
        import('./components/TestSuites');
        import('./components/CreateTestSuite');
        import('./components/UpdateTestSuite');
        import('./components/TestSuiteDetail');
        import('./components/AddUsecasesToSuite');
        import('./components/ConfigureSchedule');
      }, 2000);
    }
  }, []);

  useEffect(() => {
    setActiveHref(location.pathname);
  }, [location.pathname]);

  return (
    <AppLayout
      navigation={
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
      }
      toolsHide
      content={
        <Suspense fallback={
          <Box textAlign="center" padding="xxl">
            <Spinner size="large" />
          </Box>
        }>
          <Routes>
            <Route path="/" element={<HomeScreen />} />
            <Route path="/usecases" element={<Usecases />} />
            <Route path="/create" element={<CreateUsecaseWizard />} />
            <Route path="/create/blank" element={<CreateUsecase />} />
            <Route path="/create/import" element={<ImportUsecase />} />
            <Route path="/create/template" element={<CreateFromTemplate />} />
            <Route path="/create/clone" element={<CloneUsecase />} />
            <Route path="/create/journey" element={
              <ErrorBoundary>
                <UserJourneyWizard />
              </ErrorBoundary>
            } />
            <Route path="/create/wizard/setup" element={<WizardSetup />} />
            <Route path="/wizard/:sessionId" element={
              <ErrorBoundary>
                <InteractiveWizard />
              </ErrorBoundary>
            } />
            <Route path="/templates" element={<TemplateLibrary />} />
            <Route path="/templates/:id" element={<TemplateDetail />} />
            <Route path="/template-usecase" element={<TemplateUsecase />} />
            <Route path="/users" element={<Users />} />
            <Route path="/users/create" element={<CreateUser />} />
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
            <Route path="/usecase/:usecaseId/execution/:executionId" element={<ExecutionDetail />} />
            <Route path="/about" element={<About />} />
          </Routes>
        </Suspense>
      }
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
          <AppContent />
        </Router>
      )}
    </Authenticator>
  );
}

export default App;
