import React from 'react';
import { costsApi } from '../../../utils/api';
import { LoadedCostCard } from './LoadedCostCard';
import { useCosts } from './useCosts';

interface UsecaseCostCardProps {
  usecaseId: string;
}

/** Compact "Cost" card for the use case detail page: windows + sparkline, no table. */
export default function UsecaseCostCard({ usecaseId }: UsecaseCostCardProps) {
  const state = useCosts(costsApi.usecase, usecaseId);
  return <LoadedCostCard state={state} />;
}
