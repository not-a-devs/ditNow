import { ApiError, requestData } from '../../lib/api';

export const KINDS = ['ADMISSION_RESULT', 'ADMISSION_WITHDRAWAL', 'CERTIFICATE', 'TUITION', 'PROTECTED_COUNSEL'] as const;
export type Kind = typeof KINDS[number];
export type Scenario = 'STANDARD' | 'REVIEW_EXAMPLE';
export interface Item {
  id: string; kind: Kind; scenario: Scenario; status: 'REQUESTED' | 'IN_PROGRESS' | 'COMPLETED';
  status_label: string; revision: number; created_at: string; updated_at: string; title: string;
  outcome_text: string | null; document_text: string | null; source_kind: 'DEMO';
  persistence: 'PROCESS_MEMORY'; official_effect: false; sensitive_content_collected: false;
}
export interface Page { source_kind: 'DEMO'; persistence: 'PROCESS_MEMORY'; official_effect: false; items: Item[] }
export interface Create { kind: Kind; scenario: Scenario; consent: true }
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const exact = (value: Record<string, unknown>, keys: string[]) => Object.keys(value).every(key => keys.includes(key)) && keys.every(key => Object.hasOwn(value, key));
const text = (value: unknown, max: number) => typeof value === 'string' && Array.from(value).length <= max;
const uuid = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
const time = (value: unknown) => typeof value === 'string' && /T.*(?:Z|[+-]\d\d:\d\d)$/.test(value) && Number.isFinite(Date.parse(value));
const boundary = (value: Record<string, unknown>) => value.source_kind === 'DEMO' && value.persistence === 'PROCESS_MEMORY' && value.official_effect === false;
export function isItem(value: unknown): value is Item {
  return object(value) && exact(value, ['id', 'kind', 'scenario', 'status', 'status_label', 'revision', 'created_at', 'updated_at', 'title', 'outcome_text', 'document_text', 'source_kind', 'persistence', 'official_effect', 'sensitive_content_collected'])
    && uuid(value.id) && KINDS.includes(value.kind as Kind) && ['STANDARD', 'REVIEW_EXAMPLE'].includes(value.scenario as string)
    && ['REQUESTED', 'IN_PROGRESS', 'COMPLETED'].includes(value.status as string)
    && text(value.status_label, 200) && text(value.title, 200) && Number.isSafeInteger(value.revision) && Number(value.revision) >= 1 && Number(value.revision) <= 2147483647
    && time(value.created_at) && time(value.updated_at) && (value.outcome_text === null || text(value.outcome_text, 2000))
    && (value.document_text === null || value.kind === 'CERTIFICATE' && value.status === 'COMPLETED' && text(value.document_text, 4000))
    && boundary(value) && value.sensitive_content_collected === false;
}
export function isPage(value: unknown): value is Page {
  return object(value) && exact(value, ['source_kind', 'persistence', 'official_effect', 'items']) && boundary(value)
    && Array.isArray(value.items) && value.items.length <= 20 && value.items.every(isItem)
    && new Set(value.items.map(item => item.id)).size === value.items.length;
}
function invalid(): never { throw new ApiError('INVALID_RESPONSE', 200); }
function path(id: string) { if (!uuid(id)) return invalid(); return `/me/demo-services/${id}`; }
export async function list(signal?: AbortSignal): Promise<Page> {
  const value = await requestData<unknown>('/me/demo-services', { signal, cache: 'no-store' });
  return isPage(value) ? value : invalid();
}
export async function create(body: Create, key: string, signal?: AbortSignal): Promise<Item> {
  const value = await requestData<unknown>('/me/demo-services', { method: 'POST', signal, cache: 'no-store',
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key }, body: JSON.stringify(body) });
  return isItem(value) && value.kind === body.kind && value.scenario === body.scenario ? value : invalid();
}
export async function advance(item: Pick<Item, 'id' | 'revision' | 'kind' | 'scenario'>, key: string, signal?: AbortSignal): Promise<Item> {
  const value = await requestData<unknown>(path(item.id) + '/advance', { method: 'POST', signal, cache: 'no-store',
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key }, body: JSON.stringify({ revision: item.revision }) });
  return isItem(value) && value.id === item.id && value.kind === item.kind && value.scenario === item.scenario
    && value.revision > item.revision && value.status !== 'REQUESTED' ? value : invalid();
}
export async function remove(item: Pick<Item, 'id' | 'revision'>, signal?: AbortSignal): Promise<void> {
  const value = await requestData<unknown>(path(item.id) + `?revision=${item.revision}`, { method: 'DELETE', signal, cache: 'no-store' });
  if (!object(value) || !exact(value, ['id', 'deleted']) || value.id !== item.id || value.deleted !== true) invalid();
}
