import React from 'react';
import ApplicationConfigPage from './ApplicationConfigPage';
import { VariablesEditor, variablesApi } from '../common/VariablesEditor';

/** Application-level variables, inherited by every use case of the application. */
export default function ApplicationVariablesPage() {
  return (
    <ApplicationConfigPage
      title="Variables"
      description="Key/value pairs shared by every use case of this application. A use case variable with the same key overrides the application value."
    >
      {({ application, readOnly }) => (
        <VariablesEditor
          key={application.id}
          api={variablesApi(`applications/${application.id}/variables`)}
          readOnly={readOnly}
        />
      )}
    </ApplicationConfigPage>
  );
}
