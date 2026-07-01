import Tiles from "@cloudscape-design/components/tiles";
import FormField from "@cloudscape-design/components/form-field";
import Box from "@cloudscape-design/components/box";
import type { TilesProps } from "@cloudscape-design/components/tiles";
import type { StepProps } from '../types';
import type { TestPlatform } from '../types';

const platformOptions: TilesProps.TilesDefinition[] = [
  {
    value: 'web',
    label: <Box fontWeight="bold">Web</Box>,
    description:
      'Test web applications in a browser. Supports starting URL, browser policies, step caching, and all creation methods including interactive wizard and templates.',
  },
  {
    value: 'mobile',
    label: (
      <Box>
        <Box fontWeight="bold" display="inline">Mobile</Box>{' '}
        <Box color="text-status-inactive" fontSize="body-s" display="inline">— Experimental</Box>
      </Box>
    ),
    description:
      'Test mobile applications on real devices via AWS Device Farm. Supports Android and iOS with app binary uploads. Some features like step caching and interactive wizard are not available.',
  },
];

export default function PlatformSelectionStep({ state, dispatch }: StepProps) {
  return (
    <FormField>
      <Tiles
        value={state.testPlatform}
        items={platformOptions}
        onChange={({ detail }: { detail: TilesProps.ChangeDetail }) =>
          dispatch({ type: 'SET_TEST_PLATFORM', payload: detail.value as TestPlatform })
        }
        columns={2}
      />
    </FormField>
  );
}
