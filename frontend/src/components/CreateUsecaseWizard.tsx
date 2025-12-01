import { useNavigate } from 'react-router-dom';
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Cards from "@cloudscape-design/components/cards";
import Box from "@cloudscape-design/components/box";
import Icon from "@cloudscape-design/components/icon";
import Link from "@cloudscape-design/components/link";
import BreadcrumbGroup from "@cloudscape-design/components/breadcrumb-group";

interface CreationOption {
  id: string;
  title: string;
  description: string;
  icon: string;
  route: string;
}

const creationOptions: CreationOption[] = [
  {
    id: 'wizard',
    title: 'Interactive Wizard',
    description: 'Build your use case step-by-step with live browser feedback. Add steps, see them execute in real-time, and accept when ready.',
    icon: 'status-in-progress',
    route: '/create/wizard/setup'
  },
  {
    id: 'blank',
    title: 'Create Blank',
    description: 'Start from scratch and manually configure all use case settings, steps, and validations.',
    icon: 'add-plus',
    route: '/create/blank'
  },
  {
    id: 'template',
    title: 'Start from Template',
    description: 'Begin with a pre-built template and add your own steps and configurations.',
    icon: 'folder',
    route: '/create/template'
  },
  {
    id: 'user-journey',
    title: 'Create from User Journey',
    description: 'Describe your test scenario in natural language and let AI generate the use case automatically.',
    icon: 'gen-ai',
    route: '/create/journey'
  },
  {
    id: 'clone',
    title: 'Clone from Use Case',
    description: 'Duplicate an existing use case and modify it to create a new test scenario.',
    icon: 'copy',
    route: '/create/clone'
  }
];

export default function CreateUsecaseWizard() {
  const navigate = useNavigate();

  return (
    <SpaceBetween direction="vertical" size="l">
      <BreadcrumbGroup
        items={[
          { text: 'Home', href: '/' },
          { text: 'Create Use Case', href: '/create' }
        ]}
        onFollow={(event) => {
          event.preventDefault();
          navigate(event.detail.href);
        }}
      />

      <Header
        variant="h1"
        description="Choose how you want to create your new use case"
      >
        Create Use Case
      </Header>

      <Cards
        cardDefinition={{
          header: item => (
            <Box>
              <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                <Icon name={item.icon as any} size="medium" />
                <Link
                  variant="primary"
                  fontSize="heading-m"
                  onFollow={() => navigate(item.route)}
                >
                  {item.title}
                </Link>
              </SpaceBetween>
            </Box>
          ),
          sections: [
            {
              id: 'description',
              content: item => (
                <Box variant="p" color="text-body-secondary">
                  {item.description}
                </Box>
              )
            }
          ]
        }}
        items={creationOptions}
        cardsPerRow={[
          { cards: 1 },
          { minWidth: 500, cards: 2 }
        ]}
      />
    </SpaceBetween>
  );
}
