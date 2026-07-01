import React from 'react';
import Select, { SelectProps } from '@cloudscape-design/components/select';
import { Application } from '../../types/application';

interface ApplicationSelectorProps {
  applications: Application[];
  selectedId: string;
  onChange: (id: string) => void;
}

export function ApplicationSelector({ applications, selectedId, onChange }: ApplicationSelectorProps) {
  const options = applications.map(app => ({
    label: app.name,
    value: app.id,
    description: app.base_url,
  }));

  const selectedOption = options.find(o => o.value === selectedId) || null;

  const handleChange: SelectProps['onChange'] = ({ detail }) => {
    if (detail.selectedOption?.value) {
      onChange(detail.selectedOption.value);
    }
  };

  return (
    <Select
      selectedOption={selectedOption}
      onChange={handleChange}
      options={options}
      placeholder="Select application..."
      filteringType="auto"
    />
  );
}
