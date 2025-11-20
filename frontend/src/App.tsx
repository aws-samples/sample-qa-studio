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

import { baseName } from "../../configuration.json"
// Removed complex chunk loader imports for compatibility

// Lazy load components for code splitting
const HomeScreen = React.lazy(() => import('./components/HomeScreen'));
const CreateUsecaseWizard = React.lazy(() => import('./components/CreateUsecaseWizard'));
const CreateUsecase = React.lazy(() => import('./components/CreateUsecase'));
const CloneUsecase = React.lazy(() => import('./components/CloneUsecase'));
const TemplateUsecase = React.lazy(() => import('./components/TemplateUsecase'));
const UserJourneyWizard = React.lazy(() => import('./components/UserJourneyWizard'));
const UsecaseDetail = React.lazy(() => import('./components/UsecaseDetailRefactored'));
const ExecutionDetail = React.lazy(() => import('./components/ExecutionDetailRefactored'));
const Users = React.lazy(() => import('./components/Users'));
const TemplateLibrary = React.lazy(() => import('./components/templates/TemplateLibrary'));
const TemplateDetail = React.lazy(() => import('./components/templates/TemplateDetail'));

Amplify.configure(amplifyconfig);



function Usecases() {
  return (
    <div>
      <h1>Usecases</h1>
      <p>This is the usecases page.</p>
    </div>
  );
}

function AppContent() {
  const navigate = useNavigate();
  const location = useLocation();
  const [activeHref, setActiveHref] = useState(location.pathname);

  // Preload components when the app becomes idle
  React.useEffect(() => {
    // Simple idle preloading
    if ('requestIdleCallback' in window) {
      (window as any).requestIdleCallback(() => {
        import('./components/CreateUsecaseWizard');
        import('./components/CreateUsecase');
        import('./components/CloneUsecase');
        import('./components/TemplateUsecase');
        import('./components/UserJourneyWizard');
        import('./components/UsecaseDetailRefactored');
        import('./components/ExecutionDetailRefactored');
        import('./components/Users');
        import('./components/templates/TemplateLibrary');
        import('./components/templates/TemplateDetail');
      });
    } else {
      setTimeout(() => {
        import('./components/CreateUsecaseWizard');
        import('./components/CreateUsecase');
        import('./components/CloneUsecase');
        import('./components/TemplateUsecase');
        import('./components/UserJourneyWizard');
        import('./components/UsecaseDetailRefactored');
        import('./components/ExecutionDetailRefactored');
        import('./components/Users');
        import('./components/templates/TemplateLibrary');
        import('./components/templates/TemplateDetail');
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
          items={[
            { type: "link", text: "Home", href: "/" },
            { type: "link", text: "Create Use Case", href: "/create" },
            { type: "link", text: "Templates", href: "/templates" },
            { type: "divider" },
            { type: "link", text: "Users", href: "/users" },
            { type: "divider" },
            { type: "link", text: baseName, href: "#" },
          ]}
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
            <Route path="/create/clone" element={<CloneUsecase />} />
            <Route path="/create/journey" element={
              <ErrorBoundary>
                <UserJourneyWizard />
              </ErrorBoundary>
            } />
            <Route path="/templates" element={<TemplateLibrary />} />
            <Route path="/templates/:id" element={<TemplateDetail />} />
            <Route path="/template-usecase" element={<TemplateUsecase />} />
            <Route path="/users" element={<Users />} />
            <Route path="/usecase/:id" element={<UsecaseDetail />} />
            <Route path="/usecase/:usecaseId/execution/:executionId" element={<ExecutionDetail />} />
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
              title: "NovaAct QA Studio"
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
