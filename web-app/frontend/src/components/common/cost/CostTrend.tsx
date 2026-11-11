import React from 'react';
import Box, { BoxProps } from '@cloudscape-design/components/box';
import Icon, { IconProps } from '@cloudscape-design/components/icon';
import SpaceBetween from '@cloudscape-design/components/space-between';
import { CostTrendDirection } from '../../../utils/api';

const usdFormat = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pctFormat = new Intl.NumberFormat('en-US', { style: 'percent', maximumFractionDigits: 1, signDisplay: 'exceptZero' });

/** `1.42 → "$1.42"`, `1234.5 → "$1,234.50"`. Storage keeps 6 decimals; the UI shows 2. */
export function formatUsd(amount: number): string {
  return usdFormat.format(amount);
}

const TREND_PRESENTATION: Record<CostTrendDirection, { icon: IconProps.Name; iconVariant: IconProps.Variant; color: BoxProps.Color; label: string }> = {
  // Rising cost is a warning, not an error; falling cost is good news.
  up: { icon: 'arrow-up', iconVariant: 'warning', color: 'text-status-warning', label: 'Cost rising' },
  down: { icon: 'arrow-down', iconVariant: 'success', color: 'text-status-success', label: 'Cost falling' },
  flat: { icon: 'arrow-right', iconVariant: 'normal', color: 'inherit', label: 'Cost unchanged' },
};

export interface CostTrendProps {
  /** Allocated bill (USD) for the window. */
  amount: number;
  /** Same window at list price (USD); shown as smaller secondary text when given. */
  listAmount?: number;
  /** `null` while fewer than 2× the window length of days exist → "not enough data". */
  trend: CostTrendDirection | null;
  /** Percentage behind the arrow; `null` when the previous window was 0 → arrow only. */
  changePct: number | null;
  /** `large` (default): card figure in `awsui-value-large`. `inline`: one line for table cells and headers. */
  variant?: 'large' | 'inline';
}

function TrendIndicator({ trend, changePct }: Pick<CostTrendProps, 'trend' | 'changePct'>) {
  if (trend === null) {
    return <Box color="text-body-secondary" fontSize="body-s" display="inline-block">not enough data</Box>;
  }
  const { icon, iconVariant, color, label } = TREND_PRESENTATION[trend];
  return (
    <Box color={color} fontSize="body-s" display="inline-block">
      <Icon name={icon} variant={iconVariant} size="small" ariaLabel={label} />
      {changePct !== null && <> {pctFormat.format(changePct / 100)}</>}
    </Box>
  );
}

/**
 * One cost window: billed amount, optional list-price figure and the trend
 * arrow with its signed percentage. Presentational only.
 */
export function CostTrend({ amount, listAmount, trend, changePct, variant = 'large' }: CostTrendProps) {
  if (variant === 'inline') {
    return (
      <SpaceBetween direction="horizontal" size="xs" alignItems="center">
        <Box display="inline-block">{formatUsd(amount)}</Box>
        <TrendIndicator trend={trend} changePct={changePct} />
        {listAmount !== undefined && (
          <Box color="text-body-secondary" fontSize="body-s" display="inline-block">{formatUsd(listAmount)} at list price</Box>
        )}
      </SpaceBetween>
    );
  }
  return (
    <div>
      <Box variant="awsui-value-large">{formatUsd(amount)}</Box>
      {listAmount !== undefined && (
        <Box color="text-body-secondary" fontSize="body-s">{formatUsd(listAmount)} at list price</Box>
      )}
      <TrendIndicator trend={trend} changePct={changePct} />
    </div>
  );
}
