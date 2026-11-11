import React from 'react';
import Alert from '@cloudscape-design/components/alert';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import { UsecaseCostsResponse } from '../../../utils/api';
import { CostCard } from './CostCard';
import { CostsState } from './useCosts';

interface LoadedCostCardProps<T extends UsecaseCostsResponse> {
  state: CostsState<T>;
  /** Container heading, default "Cost". */
  title?: string;
  /** Rendered below the sparkline once data is present. */
  children?: React.ReactNode;
}

/**
 * Maps a `useCosts` state onto the card: hidden → nothing, error → Alert in
 * a container with the same heading, otherwise `CostCard`.
 */
export function LoadedCostCard<T extends UsecaseCostsResponse>({ state, title = 'Cost', children }: LoadedCostCardProps<T>) {
  if (state.hidden) {
    return null;
  }
  if (state.error !== null) {
    return (
      <Container header={<Header variant="h2">{title}</Header>}>
        <Alert type="error" header="Error">{state.error}</Alert>
      </Container>
    );
  }
  return (
    <CostCard summary={state.data?.summary ?? null} days={state.data?.days ?? []} loading={state.loading} title={title}>
      {children}
    </CostCard>
  );
}
