import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import Alert from '@cloudscape-design/components/alert';
import Box from '@cloudscape-design/components/box';
import BreadcrumbGroup from '@cloudscape-design/components/breadcrumb-group';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Spinner from '@cloudscape-design/components/spinner';
import { api } from '../../utils/api';
import { Application } from '../../types/application';
import { usePermissions, canManageApplication } from '../../auth';

interface ApplicationConfigPageBody {
  application: Application;
  /** True when the user may only view this application's configuration. */
  readOnly: boolean;
}

interface ApplicationConfigPageProps {
  /** Page name, used as header and last breadcrumb (e.g. "Variables"). */
  title: string;
  description: string;
  /** Rendered once the application is loaded. */
  children: (body: ApplicationConfigPageBody) => React.ReactNode;
}

/**
 * Shell shared by the application Variables / Secrets / Datasets pages:
 * loads `GET /applications/{id}`, renders breadcrumbs `Applications → {name} → {title}`,
 * the header and the load state, and tells the body whether writes are allowed
 * (`canManageApplication`, the same rule as the Edit page).
 */
export default function ApplicationConfigPage({ title, description, children }: ApplicationConfigPageProps) {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { isAdmin, teams } = usePermissions();
  const [application, setApplication] = useState<Application | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    if (!id) {
      setError('Application ID not found');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError('');
    setApplication(null);
    api.get(`applications/${id}`)
      .then((app: Application) => { if (!cancelled) setApplication(app); })
      .catch((e: any) => { if (!cancelled) setError(e.message || 'Failed to load application'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [id]);

  const readOnly = !canManageApplication(isAdmin, teams, application?.owner_team_id);

  return (
    <SpaceBetween size="l">
      <BreadcrumbGroup
        items={[
          { text: 'Applications', href: '/applications' },
          { text: application?.name || (loading ? 'Loading...' : 'Application'), href: id ? `/applications/${id}` : '/applications' },
          { text: title, href: '#' },
        ]}
        onFollow={(event) => { event.preventDefault(); navigate(event.detail.href); }}
      />

      <Header variant="h1" description={description}>
        {title}
      </Header>

      {error && <Alert type="error" header="Error">{error}</Alert>}

      {loading && (
        <Box textAlign="center" padding="xxl"><Spinner size="large" /></Box>
      )}

      {application && readOnly && (
        <Alert type="info">
          This page is read-only for you. Only a team lead of the owning team or an admin can change
          the {title.toLowerCase()} of this application.
        </Alert>
      )}

      {application && children({ application, readOnly })}
    </SpaceBetween>
  );
}
