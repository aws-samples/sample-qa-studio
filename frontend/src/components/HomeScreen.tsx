import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Link from "@cloudscape-design/components/link";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import Table from "@cloudscape-design/components/table";
import { api } from '../utils/api';
import Badge from "@cloudscape-design/components/badge";
import ImportUsecaseModal from './ImportUsecaseModal';
// import { usePreloadOnHover } from './common/ComponentPreloader';

export default function HomeScreen() {
  const navigate = useNavigate();
  const [usecases, setUsecases] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showImportModal, setShowImportModal] = useState(false);

  // Preload UsecaseDetail when hovering over usecase links
  // const usecaseDetailPreload = usePreloadOnHover(
  //   'UsecaseDetail',
  //   () => import('./UsecaseDetailRefactored')
  // );

  useEffect(() => {
    const fetchUsecases = async () => {
      try {
        const data = await api.get('usecases');
        setUsecases(data.usecases || []);
      } catch (error) {
        console.error('Failed to fetch usecases:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchUsecases();
  }, []);

  const handleImportSuccess = () => {
    setShowImportModal(false);
    // Refresh the usecases list
    const fetchUsecases = async () => {
      try {
        const data = await api.get('usecases');
        setUsecases(data.usecases || []);
      } catch (error) {
        console.error('Failed to fetch usecases:', error);
      }
    };
    fetchUsecases();
  };

  return (
    <SpaceBetween direction="vertical" size="l">     
      <Header 
        variant="h1"
        actions={
          <SpaceBetween direction="horizontal" size="xs">
            <Button onClick={() => setShowImportModal(true)}>
              Import Use Case
            </Button>
            <Button variant="primary" onClick={() => navigate('/create-usecase')}>
              Create Use Case
            </Button>
          </SpaceBetween>
        }
      >
        Use Cases
      </Header>
      <Table
        columnDefinitions={[
          { 
            id: 'name', 
            header: 'Name', 
            cell: item => (
              <Link href={`/usecase/${item.id}`}>
                {item.name}
              </Link>
            )
          },
          { id: 'description', header: 'Description', maxWidth: 200, cell: item => item.description },
          { id: 'active', header: 'Active', cell: item => item.active ? 'Yes' : 'No' },
          { id: 'tags', header: 'Tags', cell: item => item.tags ? item.tags.map((tag: string) => (<Badge key={tag}>{tag}</Badge>)) : '' }
        ]}
        items={usecases}
        loading={loading}
        empty="No use cases found"
      />
      
      <ImportUsecaseModal
        visible={showImportModal}
        onDismiss={() => setShowImportModal(false)}
        onImportSuccess={handleImportSuccess}
      />
    </SpaceBetween>
  );
}