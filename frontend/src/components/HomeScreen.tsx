import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Link from "@cloudscape-design/components/link";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import ButtonDropdown from "@cloudscape-design/components/button-dropdown";
import Table from "@cloudscape-design/components/table";
import { api } from '../utils/api';
import Badge from "@cloudscape-design/components/badge";
import ImportUsecaseModal from './ImportUsecaseModal';
import Flashbar from "@cloudscape-design/components/flashbar";
// import { usePreloadOnHover } from './common/ComponentPreloader';

interface BatchExecutionResult {
  usecaseId: string;
  usecaseName: string;
  success: boolean;
  error?: string;
}

export default function HomeScreen() {
  const navigate = useNavigate();
  const [usecases, setUsecases] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showImportModal, setShowImportModal] = useState(false);
  const [selectedItems, setSelectedItems] = useState<any[]>([]);
  const [batchExecuting, setBatchExecuting] = useState(false);
  const [flashbarItems, setFlashbarItems] = useState<any[]>([]);

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

  const handleBatchExecute = async () => {
    if (selectedItems.length === 0) {
      setFlashbarItems([{
        type: 'warning',
        content: 'Please select at least one use case to execute',
        dismissible: true,
        onDismiss: () => setFlashbarItems([])
      }]);
      return;
    }

    setBatchExecuting(true);
    setFlashbarItems([{
      type: 'info',
      content: `Starting batch execution for ${selectedItems.length} use case(s)...`,
      loading: true
    }]);

    // Execute all selected use cases in parallel
    const executionPromises = selectedItems.map(async (usecase) => {
      try {
        await api.post(`usecase/${usecase.id}/execute?trigger-type=OnDemandHeadless`, {});
        return {
          usecaseId: usecase.id,
          usecaseName: usecase.name,
          success: true
        } as BatchExecutionResult;
      } catch (error) {
        return {
          usecaseId: usecase.id,
          usecaseName: usecase.name,
          success: false,
          error: (error as Error).message
        } as BatchExecutionResult;
      }
    });

    const results = await Promise.all(executionPromises);
    
    const successCount = results.filter(r => r.success).length;
    const failureCount = results.filter(r => !r.success).length;

    // Show results
    const resultItems = [];
    
    if (successCount > 0) {
      resultItems.push({
        type: 'success' as const,
        content: `Successfully started execution for ${successCount} use case(s)`,
        dismissible: true,
        onDismiss: () => setFlashbarItems([])
      });
    }

    if (failureCount > 0) {
      const failedUsecases = results
        .filter(r => !r.success)
        .map(r => r.usecaseName)
        .join(', ');
      
      resultItems.push({
        type: 'error' as const,
        content: `Failed to start execution for ${failureCount} use case(s): ${failedUsecases}`,
        dismissible: true,
        onDismiss: () => setFlashbarItems([])
      });
    }

    setFlashbarItems(resultItems);
    setBatchExecuting(false);
    setSelectedItems([]);
  };

  return (
    <SpaceBetween direction="vertical" size="l">
      <Flashbar items={flashbarItems} />
      
      <Header 
        variant="h1"
        actions={
          <ButtonDropdown
            variant="primary"
            loading={batchExecuting}
            disabled={batchExecuting}
            onItemClick={({ detail }) => {
              if (detail.id === 'import') {
                setShowImportModal(true);
              } else if (detail.id === 'execute-selected') {
                handleBatchExecute();
              }
            }}
            items={[
              {
                id: 'execute-selected',
                text: `Execute Selected (${selectedItems.length})`,
                disabled: selectedItems.length === 0
              },
              {
                id: 'import',
                text: 'Import Use Case'
              }
            ]}
            mainAction={{
              text: 'Create Use Case',
              onClick: () => navigate('/create-usecase')
            }}
          />
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
        loadingText="Loading use cases..."
        empty="No use cases found"
        selectionType="multi"
        selectedItems={selectedItems}
        onSelectionChange={({ detail }) => setSelectedItems(detail.selectedItems)}
      />
      
      <ImportUsecaseModal
        visible={showImportModal}
        onDismiss={() => setShowImportModal(false)}
        onImportSuccess={handleImportSuccess}
      />
    </SpaceBetween>
  );
}