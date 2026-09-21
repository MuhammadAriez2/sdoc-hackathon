import type {Case} from './types';

export const labels: Record<string, string> = {
  shipper: 'Shipper',
  consignee: 'Consignee',
  notify_party: 'Notify party',
  port_of_loading: 'Port of loading',
  port_of_discharge: 'Port of discharge',
  container_count: 'Container count',
  gross_weight_kg: 'Gross weight · kg',
};

export const categories = ['BL_COMPARISON', 'SI_REQUEST', 'INVOICE_QUERY', 'GENERAL', 'SPAM'];

// quayproof-category-filters-v1
export const categoryFilters = [
  ['all', 'All emails'],
  ['BL_COMPARISON', 'BL comparisons'],
  ['SI_REQUEST', 'SI requests'],
  ['INVOICE_QUERY', 'Invoice queries'],
  ['GENERAL', 'General'],
  ['SPAM', 'Spam'],
] as const;

export const filterLabels: Record<string, string> = {
  ...Object.fromEntries(categoryFilters),
  defects: 'Confirmed defects',
  review: 'Need human review',
  clear: 'All seven match',
  failures: 'Processing failures',
};

export function matchesFilter(c: Case, filter: string) {
  if (filter === 'all') return true;
  if (filter === 'defects') return !!c.result?.has_defect;
  if (filter === 'review') return !!c.result?.requires_review;
  if (filter === 'clear') return c.result?.status === 'OK';
  if (filter === 'failures') return c.state === 'failed';
  return c.classification?.category === filter;
}

export const nice = (s: string) => s.replaceAll('_', ' ').toLowerCase();

export const stateLabel = (c: Case) =>
  c.state === 'complete' ? c.result?.status || c.classification?.category || 'Complete' : c.state;

/** Shared review-form state, lifted so the drawer and the audit panel agree. */
export type ReviewForm = {
  actor: string; setActor: (v: string) => void;
  reason: string; setReason: (v: string) => void;
  raw: string; setRaw: (v: string) => void;
  blockIds: string; setBlockIds: (v: string) => void;
  field: string; setField: (v: string) => void;
};
