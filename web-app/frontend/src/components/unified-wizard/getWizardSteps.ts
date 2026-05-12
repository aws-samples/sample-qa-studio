import type {
  CreationPath,
  CreationMethod,
  TestPlatform,
  WizardStepConfig,
} from './types';

import HowToStartStep from './steps/HowToStartStep';
import BasicInfoStep from './steps/BasicInfoStep';
import PlatformSelectionStep from './steps/PlatformSelectionStep';
import CreationMethodStep from './steps/CreationMethodStep';
import PlatformConfigStep from './steps/PlatformConfigStep';
import SetupAndRecordStep from './steps/SetupAndRecordStep';
import SelectTemplateStep from './steps/SelectTemplateStep';
import DescribeAndGenerateStep from './steps/DescribeAndGenerateStep';
import SelectSourceStep from './steps/SelectSourceStep';
import UploadFileStep from './steps/UploadFileStep';
import ReviewAndCreateStep from './steps/ReviewAndCreateStep';

/**
 * Returns the dynamic wizard step array based on the user's current selections.
 *
 * - Always starts with "How to start"
 * - Always ends with "Review & create"
 * - Middle steps vary by creationPath and creationMethod
 */
export function getWizardSteps(
  creationPath: CreationPath,
  creationMethod: CreationMethod,
  testPlatform: TestPlatform
): WizardStepConfig[] {
  const steps: WizardStepConfig[] = [
    { title: 'How to start', description: 'Choose how you want to create your new test case.', component: HowToStartStep },
  ];

  if (creationPath === 'create-new') {
    steps.push({ title: 'Platform selection', description: 'Choose the platform your test case targets.', component: PlatformSelectionStep });
    steps.push({ title: 'Basic info', description: 'Enter the core metadata for your test case.', component: BasicInfoStep });
    steps.push({ title: 'Creation method', description: 'Choose how you want to build your test case.', component: CreationMethodStep });

    if (creationMethod === 'blank') {
      if (testPlatform === 'mobile') {
        steps.push({ title: 'App configuration', description: 'Configure your mobile app settings, device, and binary.', component: PlatformConfigStep });
      } else {
        steps.push({ title: 'Browser configuration', description: 'Configure browser-specific settings for your test case.', component: PlatformConfigStep });
      }
    } else if (creationMethod === 'interactive-wizard') {
      steps.push({ title: 'Setup & record', description: 'Start a live browser session and build test steps interactively.', component: SetupAndRecordStep });
    } else if (creationMethod === 'template') {
      steps.push({ title: 'Select template', description: 'Choose a pre-built template to start from.', component: SelectTemplateStep });
    } else if (creationMethod === 'user-journey') {
      steps.push({ title: 'Describe & generate', description: 'Describe your test scenario and let AI generate the use case.', component: DescribeAndGenerateStep });
    }
    // When creationMethod is null, no method-specific step is added
  } else if (creationPath === 'clone') {
    steps.push({ title: 'Select source', description: 'Choose an existing use case to create a copy from.', component: SelectSourceStep });
  } else if (creationPath === 'import') {
    steps.push({ title: 'Upload file', description: 'Upload a previously exported use case JSON file.', component: UploadFileStep });
  }
  // When creationPath is null, only "How to start" and "Review & create"

  steps.push({ title: 'Review & create', description: 'Review your configuration below, then click Create to proceed.', component: ReviewAndCreateStep });

  return steps;
}

/**
 * Returns the available creation methods for a given test platform.
 *
 * - Web: all four methods
 * - Mobile: only blank and user-journey (interactive-wizard and template are web-only)
 */
export function getAvailableMethods(testPlatform: TestPlatform): CreationMethod[] {
  if (testPlatform === 'web') {
    return ['blank', 'interactive-wizard', 'template', 'user-journey'];
  }
  return ['blank', 'user-journey'];
}
