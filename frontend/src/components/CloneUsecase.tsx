import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import FormField from "@cloudscape-design/components/form-field";
import Select, { SelectProps } from "@cloudscape-design/components/select";
import Input from "@cloudscape-design/components/input";
import Box from "@cloudscape-design/components/box";
import ColumnLayout from "@cloudscape-design/components/column-layout";
import Badge from "@cloudscape-design/components/badge";
import Spinner from "@cloudscape-design/components/spinner";
import BreadcrumbGroup from "@cloudscape-design/components/breadcrumb-group";
import { api } from '../utils/api';

interface Usecase {
  id: string;
  name: string;
  description: string;
  starting_url?: string;
  active?: boolean;
  headless?: boolean;
  tags?: string[];
}

interface UsecaseDetail extends Usecase {
  steps?: any[];
  variables?: any[];
  headers?: Record<string, string>;
}

export default function CloneUsecase() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const sourceId = searchParams.get('sourceId');
  
  const [usecases, setUsecases] = useState<Usecase[]>([]);
  const [loading, setLoading] = useState(true);
  const [cloning, setCloning] = useState(false);
  const [selectedUsecase, setSelectedUsecase] = useState<SelectProps.Option | null>(null);
  const [newName, setNewName] = useState('');
  const [usecaseDetail, setUsecaseDetail] = useState<UsecaseDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    const fetchUsecases = async () => {
      try {
        const data = await api.get('usecases');
        const usecaseList = data.usecases || [];
        setUsecases(usecaseList);
        
        // Pre-select usecase if sourceId is provided
        if (sourceId) {
          const sourceUsecase = usecaseList.find((uc: Usecase) => uc.id === sourceId);
          if (sourceUsecase) {
            setSelectedUsecase({
              label: sourceUsecase.name,
              value: sourceUsecase.id,
              description: sourceUsecase.description
            });
            setNewName(`${sourceUsecase.name} (Copy)`);
          }
        }
      } catch (error) {
        console.error('Failed to fetch usecases:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchUsecases();
  }, [sourceId]);

  useEffect(() => {
    const fetchUsecaseDetail = async () => {
      if (!selectedUsecase?.value) {
        setUsecaseDetail(null);
        return;
      }

      setLoadingDetail(true);
      try {
        const [usecaseData, stepsData, variablesData, headersData] = await Promise.all([
          api.get(`usecase/${selectedUsecase.value}`),
          api.get(`usecase/${selectedUsecase.value}/steps`),
          api.get(`usecase/${selectedUsecase.value}/variables`).catch(() => ({ variables: [] })),
          api.get(`usecase/${selectedUsecase.value}/headers`).catch(() => ({ headers: {} }))
        ]);
        
        setUsecaseDetail({
          ...usecaseData,
          steps: stepsData.steps || [],
          variables: variablesData.variables || [],
          headers: headersData.headers || {}
        });
      } catch (error) {
        console.error('Failed to fetch usecase detail:', error);
      } finally {
        setLoadingDetail(false);
      }
    };

    fetchUsecaseDetail();
  }, [selectedUsecase]);

  const handleClone = async () => {
    if (!selectedUsecase || !newName.trim()) return;

    setCloning(true);
    try {
      const response = await api.post(`usecase/${selectedUsecase.value}/clone`, {
        name: newName
      });
      
      if (response.usecaseId) {
        navigate(`/usecase/${response.usecaseId}`);
      }
    } catch (error) {
      console.error('Failed to clone usecase:', error);
    } finally {
      setCloning(false);
    }
  };

  const usecaseOptions: SelectProps.Option[] = usecases.map(uc => ({
    label: uc.name,
    value: uc.id,
    description: uc.description
  }));

  return (
    <SpaceBetween direction="vertical" size="l">
      <BreadcrumbGroup
        items={[
          { text: 'Home', href: '/' },
          { text: 'Create Use Case', href: '/create' },
          { text: 'Clone from Use Case', href: '/create/clone' }
        ]}
        onFollow={(event) => {
          event.preventDefault();
          navigate(event.detail.href);
        }}
      />

      <Header
        variant="h1"
        description="Clone an existing use case to create a copy with all its steps and configurations."
      >
        Clone from Use Case
      </Header>

      <Container>
        <SpaceBetween direction="vertical" size="l">
          <FormField label="Select Use Case to Clone">
            <Select
              selectedOption={selectedUsecase}
              onChange={({ detail }) => {
                setSelectedUsecase(detail.selectedOption);
                if (detail.selectedOption) {
                  const original = usecases.find(uc => uc.id === detail.selectedOption.value);
                  if (original) {
                    setNewName(`${original.name} (Copy)`);
                  }
                }
              }}
              options={usecaseOptions}
              placeholder="Choose a use case"
              loadingText="Loading use cases..."
              statusType={loading ? 'loading' : 'finished'}
              disabled={loading || cloning}
              filteringType="auto"
            />
          </FormField>

        </SpaceBetween>
      </Container>

      {selectedUsecase && (
        <Container header={<Header variant="h2">Use Case Summary</Header>}>
          {loadingDetail ? (
            <Box textAlign="center" padding="l">
              <Spinner />
            </Box>
          ) : usecaseDetail ? (
            <ColumnLayout columns={2} variant="text-grid">
              <div>
                <Box variant="awsui-key-label">Name</Box>
                <div>{usecaseDetail.name}</div>
              </div>
              <div>
                <Box variant="awsui-key-label">Status</Box>
                <div>
                  {usecaseDetail.active ? (
                    <Badge color="green">Active</Badge>
                  ) : (
                    <Badge color="red">Inactive</Badge>
                  )}
                </div>
              </div>
              <div>
                <Box variant="awsui-key-label">Starting URL</Box>
                <div>{usecaseDetail.starting_url || '-'}</div>
              </div>
              <div>
                <Box variant="awsui-key-label">Mode</Box>
                <div>{usecaseDetail.headless ? 'Headless' : 'Standard'}</div>
              </div>
              <div>
                <Box variant="awsui-key-label">Steps</Box>
                <div>{usecaseDetail.steps?.length || 0} step(s)</div>
              </div>
              <div>
                <Box variant="awsui-key-label">Variables</Box>
                <div>{usecaseDetail.variables?.length || 0} variable(s)</div>
              </div>
              <div>
                <Box variant="awsui-key-label">Headers</Box>
                <div>{Object.keys(usecaseDetail.headers || {}).length} header(s)</div>
              </div>
              {usecaseDetail.tags && usecaseDetail.tags.length > 0 && (
                <div>
                  <Box variant="awsui-key-label">Tags</Box>
                  <SpaceBetween direction="horizontal" size="xs">
                    {usecaseDetail.tags.map(tag => (
                      <Badge key={tag}>{tag}</Badge>
                    ))}
                  </SpaceBetween>
                </div>
              )}
              {usecaseDetail.description && (
                <div style={{ gridColumn: '1 / -1' }}>
                  <Box variant="awsui-key-label">Description</Box>
                  <div>{usecaseDetail.description}</div>
                </div>
              )}
            </ColumnLayout>
          ) : null}
        </Container>
      )}

      {selectedUsecase && (
        <Container>
          <SpaceBetween direction="vertical" size="l">
            <FormField label="New Use Case Name">
              <Input
                value={newName}
                onChange={({ detail }) => setNewName(detail.value)}
                placeholder="Enter name for the cloned use case"
                disabled={!selectedUsecase || cloning}
              />
            </FormField>

            <Box>
              <Button
                variant="primary"
                onClick={handleClone}
                loading={cloning}
                disabled={!selectedUsecase || !newName.trim() || cloning}
              >
                Create
              </Button>
            </Box>
          </SpaceBetween>
        </Container>
      )}
    </SpaceBetween>
  );
}
