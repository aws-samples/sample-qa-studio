import React from 'react';
import ApplicationConfigPage from './ApplicationConfigPage';
import { KeyValueManager } from '../common/KeyValueManager';
import { APPLICATION_SECRET_LABELS, secretsApi } from '../SecretsManager';

/** Application-level secrets, inherited by every use case of the application. */
export default function ApplicationSecretsPage() {
  return (
    <ApplicationConfigPage
      title="Secrets"
      description="Secrets shared by every use case of this application. Values are stored in Secrets Manager and never shown again. A use case secret with the same key shadows the application secret."
    >
      {({ application, readOnly }) => (
        <KeyValueManager
          key={application.id}
          api={secretsApi(`applications/${application.id}/secrets`)}
          masked
          readOnly={readOnly}
          labels={APPLICATION_SECRET_LABELS}
        />
      )}
    </ApplicationConfigPage>
  );
}
