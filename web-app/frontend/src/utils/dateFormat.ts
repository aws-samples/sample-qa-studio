/**
 * Consistent date/time formatting across the application.
 *
 * Format: yyyy-MM-dd HH:mm:ss (24-hour, zero-padded, local timezone).
 * Example: 2026-05-18 14:09:04
 */

/**
 * Format a date string or Date object to "yyyy-MM-dd HH:mm:ss".
 * Returns '-' for falsy/invalid input.
 */
export function formatDateTime(input?: string | Date | null): string {
  if (!input) return '-';
  const date = typeof input === 'string' ? new Date(input) : input;
  if (isNaN(date.getTime())) return '-';

  const y = date.getFullYear();
  const M = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  const h = String(date.getHours()).padStart(2, '0');
  const m = String(date.getMinutes()).padStart(2, '0');
  const s = String(date.getSeconds()).padStart(2, '0');

  return `${y}-${M}-${d} ${h}:${m}:${s}`;
}

/**
 * Format a date string to "yyyy-MM-dd" (date only, no time).
 * Returns '-' for falsy/invalid input.
 */
export function formatDate(input?: string | Date | null): string {
  if (!input) return '-';
  const date = typeof input === 'string' ? new Date(input) : input;
  if (isNaN(date.getTime())) return '-';

  const y = date.getFullYear();
  const M = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');

  return `${y}-${M}-${d}`;
}
