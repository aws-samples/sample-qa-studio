import FormField from "@cloudscape-design/components/form-field";
import Tiles from "@cloudscape-design/components/tiles";
import Box from "@cloudscape-design/components/box";
import type { TilesProps } from "@cloudscape-design/components/tiles";
import type { StepProps } from '../types';
import type { CreationPath } from '../types';

const creationPathOptions: TilesProps.TilesDefinition[] = [
  {
    value: 'create-new',
    label: <Box fontWeight="bold">Create New</Box>,
    description:
      'Build a new test case from scratch. Choose between a blank form, interactive browser wizard, pre-built templates, or AI-powered generation from a natural language description.',
  },
  {
    value: 'clone',
    label: <Box fontWeight="bold">Clone</Box>,
    description:
      'Duplicate an existing use case including all steps, variables, headers, and platform configuration. Useful for creating variations of tests you have already built.',
  },
  {
    value: 'import',
    label: <Box fontWeight="bold">Import</Box>,
    description:
      'Upload a previously exported use case from a JSON file. Ideal for sharing tests between environments or team members. Secrets and app binaries must be re-configured after import.',
  },
];

export default function HowToStartStep({ state, dispatch, validationErrors }: StepProps) {
  const handleChange = ({ detail }: { detail: TilesProps.ChangeDetail }) => {
    dispatch({ type: 'SET_CREATION_PATH', payload: detail.value as CreationPath });
  };

  return (
    <FormField
      errorText={validationErrors.creationPath}
    >
      <Tiles
        value={state.creationPath}
        items={creationPathOptions}
        onChange={handleChange}
        columns={3}
      />
    </FormField>
  );
}
