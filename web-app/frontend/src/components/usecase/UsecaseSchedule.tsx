import React, { useState, useCallback, useEffect } from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import Button from "@cloudscape-design/components/button";
import KeyValuePairs from "@cloudscape-design/components/key-value-pairs";
import Link from "@cloudscape-design/components/link";
import FormField from "@cloudscape-design/components/form-field";
import Input from "@cloudscape-design/components/input";
import Select from "@cloudscape-design/components/select";
import SpaceBetween from "@cloudscape-design/components/space-between";
import { api } from '../../utils/api';
import { ContainerLoading } from '../common/LoadingStates';

interface UsecaseScheduleProps {
  usecaseId: string;
}

interface ScheduleData {
  rate: number;
  unit: string;
  enabled: boolean;
}

export default function UsecaseSchedule({ usecaseId }: UsecaseScheduleProps) {
  const [schedule, setSchedule] = useState<ScheduleData | null>(null);
  const [loading, setLoading] = useState(true);
  const [showScheduleForm, setShowScheduleForm] = useState(false);
  const [rateValue, setRateValue] = useState('');
  const [rateUnit, setRateUnit] = useState('minutes');
  const [savingSchedule, setSavingSchedule] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch schedule data
  const fetchSchedule = useCallback(async () => {
    if (!usecaseId) return;

    setLoading(true);
    setError(null);

    try {
      const scheduleData = await api.get(`usecase/${usecaseId}/schedule`);
      setSchedule(scheduleData);
    } catch (err) {
        console.error('Failed to fetch schedule:', err);
    } finally {
      setLoading(false);
    }
  }, [usecaseId]);

  // Fetch schedule when usecaseId changes
  useEffect(() => {
    fetchSchedule();
  }, [fetchSchedule]);

  // Handle creating a new schedule
  const handleCreateSchedule = useCallback(async () => {
    if (!rateValue.trim() || !rateUnit) return;

    const rate = parseInt(rateValue);
    if (isNaN(rate) || rate <= 0) {
      setError('Please enter a valid positive number for the rate');
      return;
    }

    setSavingSchedule(true);
    setError(null);

    try {
      await api.post(`usecase/${usecaseId}/schedule`, {
        rate: rate,
        unit: rateUnit
      });

      // Refresh schedule data
      await fetchSchedule();

      // Reset form
      setShowScheduleForm(false);
      setRateValue('');
      setRateUnit('minutes');
    } catch (err) {
      console.error('Failed to create schedule:', err);
      setError('Failed to create schedule');
    } finally {
      setSavingSchedule(false);
    }
  }, [usecaseId, rateValue, rateUnit, fetchSchedule]);

  // Handle deleting the schedule
  const handleDeleteSchedule = useCallback(async () => {
    try {
      await api.delete(`usecase/${usecaseId}/schedule`);
      setSchedule(null);
    } catch (err) {
      console.error('Failed to delete schedule:', err);
      setError('Failed to delete schedule');
    }
  }, [usecaseId]);

  // Handle canceling the form
  const handleCancelForm = useCallback(() => {
    setShowScheduleForm(false);
    setRateValue('');
    setRateUnit('minutes');
    setError(null);
  }, []);

  // Available time units
  const timeUnits = [
    { label: 'Minutes', value: 'minutes' },
    { label: 'Hours', value: 'hours' },
    { label: 'Days', value: 'days' }
  ];

  if (loading) {
    return (
      <ContainerLoading
        title="Schedule"
        text="Loading schedule information..."
      />
    );
  }

  return (
    <Container
      header={
        <Header
          variant="h2"
          actions={
            <SpaceBetween direction="horizontal" size="xs">
              <Button
                iconName="refresh"
                onClick={fetchSchedule}
                disabled={loading || savingSchedule}
                ariaLabel="Refresh schedule"
              />
              {!schedule && (
                <Button
                  variant="primary"
                  onClick={() => setShowScheduleForm(!showScheduleForm)}
                >
                  {showScheduleForm ? 'Cancel' : 'Add Schedule'}
                </Button>
              )}
            </SpaceBetween>
          }
        />
      }
    >
      <SpaceBetween direction="vertical" size="m">
        {error && (
          <div style={{
            padding: '12px',
            backgroundColor: '#ffeaea',
            border: '1px solid #ff6b6b',
            borderRadius: '4px',
            color: '#d63031'
          }}>
            {error}
          </div>
        )}

        {showScheduleForm && (
          <SpaceBetween direction="vertical" size="m">
            <SpaceBetween direction="horizontal" size="s">
              <FormField
                label="Run every"
              >
                <Input
                  value={rateValue}
                  onChange={({ detail }) => setRateValue(detail.value)}
                  placeholder="1"
                  type="number"
                />
              </FormField>
              <FormField label="Time unit">
                <Select
                  selectedOption={timeUnits.find(unit => unit.value === rateUnit) || timeUnits[0]}
                  onChange={({ detail }) => setRateUnit(detail.selectedOption.value!)}
                  options={timeUnits}
                />
              </FormField>
            </SpaceBetween>

            <SpaceBetween direction="horizontal" size="xs">
              <Button
                variant="primary"
                onClick={handleCreateSchedule}
                loading={savingSchedule}
                disabled={!rateValue.trim() || savingSchedule || isNaN(parseInt(rateValue)) || parseInt(rateValue) <= 0}
              >
                {savingSchedule ? 'Creating...' : 'Create Schedule'}
              </Button>
              <Button onClick={handleCancelForm}>
                Cancel
              </Button>
            </SpaceBetween>
          </SpaceBetween>
        )}

        {schedule && (
          <KeyValuePairs
            columns={2}
            items={[
              {
                label: "Schedule",
                value: `Every ${schedule.rate} ${schedule.unit}`,
              },
              {
                label: "Status",
                value: schedule.enabled ? 'Enabled' : 'Disabled',
              },
              {
                label: "Actions",
                value: (
                  <SpaceBetween direction="horizontal" size="xs">
                    <Link onClick={handleDeleteSchedule}>Delete</Link>
                  </SpaceBetween>
                ),
              }
            ]}
          />
        )}

        {!schedule && !showScheduleForm && (
          <div style={{ textAlign: 'center', padding: '20px', color: '#666' }}>
            No schedule configured for this usecase. Click 'Add Schedule' to create one.
          </div>
        )}
      </SpaceBetween>
    </Container>
  );
}