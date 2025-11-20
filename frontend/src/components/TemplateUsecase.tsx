import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import Cards from "@cloudscape-design/components/cards";
import Box from "@cloudscape-design/components/box";
import Badge from "@cloudscape-design/components/badge";
import Alert from "@cloudscape-design/components/alert";
import Spinner from "@cloudscape-design/components/spinner";
import { api } from '../utils/api';

interface Template {
  id: string;
  name: string;
  description: string;
  tags?: string[];
}

export default function TemplateUsecase() {
  const navigate = useNavigate();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const [cloning, setCloning] = useState(false);

  useEffect(() => {
    const fetchTemplates = async () => {
      try {
        const data = await api.get('usecases');
        // Filter usecases that have a "template" tag
        const templateUsecases = (data.usecases || []).filter((uc: Template) => 
          uc.tags?.some(tag => tag.toLowerCase() === 'template')
        );
        setTemplates(templateUsecases);
      } catch (error) {
        console.error('Failed to fetch templates:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchTemplates();
  }, []);

  const handleCreateFromTemplate = async (templateId: string) => {
    setSelectedTemplate(templateId);
    setCloning(true);

    try {
      const template = templates.find(t => t.id === templateId);
      const response = await api.post(`usecase/${templateId}/clone`, {
        name: `${template?.name} (Copy)`
      });
      
      if (response.usecaseId) {
        navigate(`/usecase/${response.usecaseId}`);
      }
    } catch (error) {
      console.error('Failed to clone template:', error);
    } finally {
      setCloning(false);
    }
  };

  if (loading) {
    return (
      <Container header={<Header variant="h1">Create from Template</Header>}>
        <Box textAlign="center" padding="xxl">
          <Spinner size="large" />
        </Box>
      </Container>
    );
  }

  if (templates.length === 0) {
    return (
      <Container header={<Header variant="h1">Create from Template</Header>}>
        <SpaceBetween direction="vertical" size="l">
          <Alert type="info">
            No templates available. Create a use case and tag it with "template" to make it available here.
          </Alert>
          <Box textAlign="center">
            <Button
              variant="link"
              onClick={() => navigate('/create-usecase-wizard')}
            >
              Back to Options
            </Button>
          </Box>
        </SpaceBetween>
      </Container>
    );
  }

  return (
    <Container header={<Header variant="h1">Create from Template</Header>}>
      <SpaceBetween direction="vertical" size="l">
        <Alert type="info">
          Start with a pre-built template and customize it for your specific testing needs.
        </Alert>

        <Cards
          cardDefinition={{
            header: item => (
              <Box>
                <SpaceBetween direction="vertical" size="xs">
                  <Box variant="h3" fontSize="heading-m" fontWeight="bold">
                    {item.name}
                  </Box>
                  {item.tags && item.tags.length > 0 && (
                    <SpaceBetween direction="horizontal" size="xs">
                      {item.tags.filter(tag => tag.toLowerCase() !== 'template').map(tag => (
                        <Badge key={tag} color="blue">{tag}</Badge>
                      ))}
                    </SpaceBetween>
                  )}
                </SpaceBetween>
              </Box>
            ),
            sections: [
              {
                id: 'description',
                content: item => (
                  <Box variant="p" color="text-body-secondary">
                    {item.description || 'No description available'}
                  </Box>
                )
              },
              {
                id: 'action',
                content: item => (
                  <Box textAlign="right">
                    <Button
                      variant="primary"
                      onClick={() => handleCreateFromTemplate(item.id)}
                      loading={cloning && selectedTemplate === item.id}
                      disabled={cloning}
                    >
                      Use Template
                    </Button>
                  </Box>
                )
              }
            ]
          }}
          items={templates}
          cardsPerRow={[
            { cards: 1 },
            { minWidth: 500, cards: 2 }
          ]}
        />

        <Box textAlign="center">
          <Button
            variant="link"
            onClick={() => navigate('/create-usecase-wizard')}
            disabled={cloning}
          >
            Back to Options
          </Button>
        </Box>
      </SpaceBetween>
    </Container>
  );
}
