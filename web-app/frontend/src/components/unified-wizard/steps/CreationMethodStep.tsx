import Tiles from "@cloudscape-design/components/tiles";
import FormField from "@cloudscape-design/components/form-field";
import Box from "@cloudscape-design/components/box";
import type { TilesProps } from "@cloudscape-design/components/tiles";
import type { StepProps, CreationMethod } from '../types';
import { getAvailableMethods } from '../getWizardSteps';

interface MethodOption {
  value: string;
  label: string;
  description: string;
  webOnly?: boolean;
}

const allMethods: MethodOption[] = [
  {
    value: 'blank',
    label: 'Create Blank',
    description: 'Start from scratch with full control. Configure all settings manually, then add test steps one by one. Best when you know exactly what you want to test and need precise control over every step and validation.',
  },
  {
    value: 'interactive-wizard',
    label: 'Interactive Wizard',
    description: 'Build your test with a live browser session. Enter a step instruction, watch it execute in real time, and accept it when it looks right. Great for exploring an application and building tests as you go.',
    webOnly: true,
  },
  {
    value: 'template',
    label: 'Start from Template',
    description: 'Pick a pre-built template from the library with predefined steps and variables. Customize it for your scenario. Ideal for common test patterns like login flows, checkout processes, or form submissions.',
    webOnly: true,
  },
  {
    value: 'user-journey',
    label: 'User Journey',
    description: 'Describe what you want to test in plain English and let AI generate the complete test case. Optionally record a browser session for more accurate results. The fastest way to create tests without writing individual steps.',
  },
];

function buildTileItems(testPlatform: 'web' | 'mobile'): TilesProps.TilesDefinition[] {
  const availableMethods = getAvailableMethods(testPlatform);
  const availableSet = new Set(availableMethods);

  return allMethods
    .filter((method) => availableSet.has(method.value as CreationMethod))
    .map((method) => ({
      value: method.value,
      label: <Box fontWeight="bold">{method.label}</Box>,
      description: method.description,
    }));
}

export default function CreationMethodStep({ state, dispatch, validationErrors }: StepProps) {
  const tileItems = buildTileItems(state.testPlatform);

  const handleChange = ({ detail }: { detail: TilesProps.ChangeDetail }) => {
    dispatch({ type: 'SET_CREATION_METHOD', payload: detail.value as CreationMethod });
  };

  return (
    <FormField
      errorText={validationErrors.creationMethod}
    >
      <Tiles
        value={state.creationMethod}
        items={tileItems}
        onChange={handleChange}
        columns={2}
      />
    </FormField>
  );
}
