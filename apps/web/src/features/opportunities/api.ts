// API-OPP client. Depends on shared src/lib/api.ts (requestData<T> returns success.data),
// owned by the shell branch. Paths match the FastAPI router once root mounts it at /api/v1.
// requestData resolves paths against the configured base (default /api/v1), so paths here are
// relative to that base; adding /api/v1 again would produce /api/v1/api/v1/... (see api.test.ts).
import { requestData } from '../../lib/api';
import type {
  CheckItem,
  OpportunityDetail,
  OpportunityFilter,
  OpportunityPage,
  PreparationStatus,
  SavedOpportunity,
  SavedOpportunityList,
} from './types';

const BASE = '';
const JSON_HEADERS = { 'Content-Type': 'application/json' };

function savedPath(opportunityId: string): string {
  return `${BASE}/me/saved-opportunities/${encodeURIComponent(opportunityId)}`;
}

function ifMatch(revision: number): Record<string, string> {
  return { ...JSON_HEADERS, 'If-Match': String(revision) };
}

export function listOpportunities(filter: OpportunityFilter): Promise<OpportunityPage> {
  const params = new URLSearchParams();
  if (filter.kind) params.set('kind', filter.kind);
  if (filter.q?.trim()) params.set('q', filter.q.trim());
  if (filter.department?.trim()) params.set('department', filter.department.trim());
  if (filter.openOnly) params.set('open_only', 'true');
  if (filter.cursor) params.set('cursor', filter.cursor);
  const query = params.toString();
  return requestData<OpportunityPage>(`${BASE}/opportunities${query ? `?${query}` : ''}`);
}

export function getOpportunity(id: string): Promise<OpportunityDetail> {
  return requestData<OpportunityDetail>(`${BASE}/opportunities/${encodeURIComponent(id)}`);
}

export function listSaved(): Promise<SavedOpportunityList> {
  return requestData<SavedOpportunityList>(`${BASE}/me/saved-opportunities`);
}

export function saveOpportunity(id: string, memo = ''): Promise<SavedOpportunity> {
  return requestData<SavedOpportunity>(savedPath(id), {
    method: 'PUT',
    headers: JSON_HEADERS,
    body: JSON.stringify({ memo }),
  });
}

export function updateSaved(
  id: string,
  revision: number,
  patch: { status?: PreparationStatus; memo?: string },
): Promise<SavedOpportunity> {
  return requestData<SavedOpportunity>(savedPath(id), {
    method: 'PATCH',
    headers: ifMatch(revision),
    body: JSON.stringify(patch),
  });
}

export function deleteSaved(id: string, revision: number): Promise<{ deleted: boolean }> {
  return requestData(savedPath(id), { method: 'DELETE', headers: ifMatch(revision) });
}

export function addCheck(
  id: string,
  text: string,
  sortOrder: number,
  idempotencyKey: string,
): Promise<CheckItem> {
  return requestData<CheckItem>(`${savedPath(id)}/checks`, {
    method: 'POST',
    headers: { ...JSON_HEADERS, 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify({ text, sort_order: sortOrder }),
  });
}

export function updateCheck(
  id: string,
  check: CheckItem,
  patch: { text?: string; sort_order?: number; completed?: boolean },
): Promise<CheckItem> {
  return requestData<CheckItem>(`${savedPath(id)}/checks/${encodeURIComponent(check.id)}`, {
    method: 'PATCH',
    headers: ifMatch(check.revision),
    body: JSON.stringify(patch),
  });
}

export function deleteCheck(id: string, check: CheckItem): Promise<{ deleted: boolean }> {
  return requestData(`${savedPath(id)}/checks/${encodeURIComponent(check.id)}`, {
    method: 'DELETE',
    headers: ifMatch(check.revision),
  });
}

export function newIdempotencyKey(): string {
  return `chk-${crypto.randomUUID()}`;
}
