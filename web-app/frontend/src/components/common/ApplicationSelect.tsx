import FormField from "@cloudscape-design/components/form-field";
import Select from "@cloudscape-design/components/select";
import { useApplications } from '../../hooks/useApplications';

interface ApplicationSelectProps {
  /** Selected application id ('' = none). */
  value: string;
  onChange: (applicationId: string) => void;
  errorText?: string;
  description?: string;
  disabled?: boolean;
}

/**
 * Required "Application" picker for flows that create a use case. Every use
 * case belongs to an application; the API checks edit access on it.
 */
export default function ApplicationSelect({ value, onChange, errorText, description, disabled }: ApplicationSelectProps) {
  const { options, loading } = useApplications();
  const selectedOption = options.find((opt) => opt.value === value) || null;

  return (
    <FormField
      label="Application"
      description={description}
      constraintText="Required"
      errorText={errorText}
    >
      <Select
        selectedOption={selectedOption}
        onChange={({ detail }) => onChange(detail.selectedOption?.value || '')}
        options={options}
        placeholder="Select an application"
        loadingText="Loading applications..."
        statusType={loading ? 'loading' : 'finished'}
        filteringType="auto"
        disabled={disabled}
        ariaLabel="Application"
      />
    </FormField>
  );
}
