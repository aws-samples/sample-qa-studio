import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import Table from "@cloudscape-design/components/table";
import Badge from "@cloudscape-design/components/badge";
import Link from "@cloudscape-design/components/link";
import { api } from '../../utils/api';
import { batchedPromiseAll } from '../../utils/batchedPromiseAll';
import CreateTemplateModal from './CreateTemplateModal';
import DeleteTemplateModal from '../DeleteTemplateModal';

interface Template {
  id: string;
  name: string;
  description: string;
  category: string;
  tags?: string[];
  created_by: string;
  created_at: string;
  version: number;
}

export default function TemplateLibrary() {
  const navigate = useNavigate();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [selectedItems, setSelectedItems] = useState<Template[]>([]);

  const fetchTemplates = async () => {
    try {
      const data = await api.get('templates');
      setTemplates(data.templates || []);
    } catch (error) {
      console.error('Failed to fetch templates:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTemplates();
  }, []);

  const handleCreateSuccess = () => {
    setShowCreateModal(false);
    fetchTemplates();
  };

  const handleDeleteClick = () => {
    if (selectedItems.length > 0) {
      setShowDeleteModal(true);
    }
  };

  const handleDeleteConfirm = async () => {
    if (selectedItems.length === 0) return;

    setDeleting(true);
    try {
      await batchedPromiseAll(selectedItems, (template) => api.delete(`templates/${template.id}`));
      setSelectedItems([]);
      setShowDeleteModal(false);
      fetchTemplates();
    } catch (error) {
      console.error('Failed to delete templates:', error);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <SpaceBetween direction="vertical" size="l">
      <Header
        variant="h1"
        actions={
          <SpaceBetween direction="horizontal" size="xs">
            <Button
              disabled={selectedItems.length === 0}
              onClick={handleDeleteClick}
            >
              Delete
            </Button>
            <Button
              variant="primary"
              onClick={() => setShowCreateModal(true)}
            >
              Create Template
            </Button>
          </SpaceBetween>
        }
      >
        Templates
      </Header>

      <Table
        columnDefinitions={[
          {
            id: 'name',
            header: 'Name',
            cell: item => (
              <div>
                <div>
                  <Link
                    fontSize="body-m"
                    onFollow={() => navigate(`/templates/${item.id}`)}
                  >
                    {item.name}
                  </Link>
                </div>
                {item.description && (
                  <div style={{ fontSize: '0.85em', color: '#5f6b7a', marginTop: '4px' }}>
                    {item.description}
                  </div>
                )}
              </div>
            )
          },
          {
            id: 'tags',
            header: 'Tags',
            cell: item => item.tags && item.tags.length > 0 ? (
              <SpaceBetween direction="horizontal" size="xs">
                {item.tags.map((tag: string) => (
                  <Badge key={tag}>{tag}</Badge>
                ))}
              </SpaceBetween>
            ) : '-'
          },
          {
            id: 'created_by',
            header: 'Created By',
            cell: item => item.created_by
          },
          {
            id: 'version',
            header: 'Version',
            cell: item => `v${item.version}`
          }
        ]}
        items={templates}
        loading={loading}
        loadingText="Loading templates..."
        empty="No templates found. Create your first template to get started."
        selectionType="multi"
        selectedItems={selectedItems}
        onSelectionChange={({ detail }) => setSelectedItems(detail.selectedItems)}
        resizableColumns
      />

      <CreateTemplateModal
        visible={showCreateModal}
        onDismiss={() => setShowCreateModal(false)}
        onSuccess={handleCreateSuccess}
      />

      <DeleteTemplateModal
        visible={showDeleteModal}
        templateName={
          selectedItems.length === 1 
            ? selectedItems[0].name 
            : `${selectedItems.length} templates`
        }
        onDismiss={() => setShowDeleteModal(false)}
        onConfirm={handleDeleteConfirm}
        deleting={deleting}
      />
    </SpaceBetween>
  );
}
