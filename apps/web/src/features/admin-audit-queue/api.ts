import { ApiError, requestData } from '../../lib/api';

export type Category = 'NOTICE' | 'POST' | 'REPORT';
export type Status = 'PENDING' | 'CLASSIFIED' | 'RESOLVED';
export type Classification = 'REVIEW_NEEDED' | 'NO_ACTION';
export type Resolution = 'KEEP_DEMO' | 'RESOLVE_DEMO';
export type NoteCode = 'DEMO_CHECKED' | 'DEMO_POLICY_REVIEW';
export type Meta = { source_kind: 'DEMO'; storage: 'PROCESS_MEMORY'; official_effect: false; restart_reset: true };
export type Item = { id: string; category: Category; demo_label: string; status: Status; classification: Classification | null; resolution: Resolution | null; note_code: NoteCode | null; revision: number; meta: Meta };
export type Page = { items: Item[]; meta: Meta };
export type Patch = { revision: number; note_code: NoteCode } & ({ classification: Classification } | { resolution: Resolution });
export type Filters = { status: Status | ''; category: Category | '' };

export const CATEGORY_LABELS: Record<Category, string> = { NOTICE: '공지', POST: '게시물', REPORT: '신고' };
export const STATUS_LABELS: Record<Status, string> = { PENDING: '대기', CLASSIFIED: '분류됨', RESOLVED: '처리 확정' };
export const CLASSIFICATION_LABELS: Record<Classification, string> = { REVIEW_NEEDED: '추가 검토 필요(시연)', NO_ACTION: '조치 없음(시연)' };
export const RESOLUTION_LABELS: Record<Resolution, string> = { KEEP_DEMO: '유지(시연)', RESOLVE_DEMO: '처리 완료(시연)' };
export const NOTE_LABELS: Record<NoteCode, string> = { DEMO_CHECKED: '시연 확인함', DEMO_POLICY_REVIEW: '시연 정책 검토' };

type Obj = { [key: string]: unknown };
const object = (v: unknown): v is Obj => !!v && typeof v === 'object' && !Array.isArray(v);
const exact = (v: Obj, names: string[]) => Object.keys(v).length === names.length && names.every(n => Object.hasOwn(v, n));
const uuid = (v: unknown) => typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
const member = (labels: object, v: unknown) => typeof v === 'string' && Object.hasOwn(labels, v);
const nullable = (labels: object, v: unknown) => v === null || member(labels, v);

export function isMeta(v: unknown): v is Meta {
  return object(v) && exact(v, ['source_kind', 'storage', 'official_effect', 'restart_reset'])
    && v.source_kind === 'DEMO' && v.storage === 'PROCESS_MEMORY' && v.official_effect === false && v.restart_reset === true;
}
// Status and step fields must be mutually consistent with the server's fixed PENDING->CLASSIFIED->RESOLVED flow.
// Each step adds exactly one revision: PENDING 1 -> CLASSIFIED 2 -> RESOLVED 3.
const consistent = (v: Obj) => v.status === 'PENDING' ? v.classification === null && v.resolution === null && v.note_code === null && v.revision === 1
  : v.status === 'CLASSIFIED' ? v.classification !== null && v.resolution === null && v.note_code !== null && v.revision === 2
    : v.status === 'RESOLVED' && v.classification !== null && v.resolution !== null && v.note_code !== null && v.revision === 3;
export function isItem(v: unknown): v is Item {
  return object(v) && exact(v, ['id', 'category', 'demo_label', 'status', 'classification', 'resolution', 'note_code', 'revision', 'meta'])
    && uuid(v.id) && member(CATEGORY_LABELS, v.category) && typeof v.demo_label === 'string' && /^DEMO_ITEM_\d{2}$/.test(v.demo_label)
    && member(STATUS_LABELS, v.status) && nullable(CLASSIFICATION_LABELS, v.classification) && nullable(RESOLUTION_LABELS, v.resolution)
    && nullable(NOTE_LABELS, v.note_code) && Number.isSafeInteger(v.revision) && (v.revision as number) >= 1 && consistent(v) && isMeta(v.meta);
}
export function isPage(v: unknown): v is Page {
  return object(v) && exact(v, ['items', 'meta']) && Array.isArray(v.items) && v.items.length <= 20 && v.items.every(isItem) && isMeta(v.meta);
}

const PREFIX = '/admin-audit-queue';
async function call<T>(path: string, guard: (v: unknown) => v is T, init: RequestInit): Promise<T> {
  const result = await requestData<unknown>(PREFIX + path, init);
  if (!guard(result)) throw new ApiError('INVALID_RESPONSE', 200);
  return result;
}
const safeId = (id: string) => { if (!uuid(id)) throw new ApiError('VALIDATION', 0); return id; };

export function listQueue(filters: Filters, signal: AbortSignal) {
  const query = new URLSearchParams();
  if (filters.status) query.set('status', filters.status);
  if (filters.category) query.set('category', filters.category);
  const suffix = query.toString();
  return call(suffix ? `?${suffix}` : '', isPage, { signal });
}
export const readItem = (id: string, signal: AbortSignal) => call(`/${safeId(id)}`, isItem, { signal });
export async function patchItem(id: string, body: Patch, key: string, signal: AbortSignal): Promise<Item> {
  const receipt = await call(`/${safeId(id)}`, isItem, { method: 'PATCH', signal, headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key }, body: JSON.stringify(body) });
  // The receipt must be exactly the submitted step: same id, next status, submitted code, revision + 1, note.
  const step = 'classification' in body
    ? receipt.status === 'CLASSIFIED' && receipt.classification === body.classification && receipt.resolution === null
    : receipt.status === 'RESOLVED' && receipt.resolution === body.resolution;
  if (!step || receipt.id !== id || receipt.revision !== body.revision + 1 || receipt.note_code !== body.note_code) throw new ApiError('INVALID_RESPONSE', 200);
  return receipt;
}
export const sameItem = (a: Item, b: Item) => a.id === b.id && a.status === b.status && a.revision === b.revision
  && a.classification === b.classification && a.resolution === b.resolution && a.note_code === b.note_code && a.category === b.category;
export const authFailure = (v: unknown) => v instanceof ApiError && [401, 403].includes(v.status);
export const conflict = (v: unknown) => v instanceof ApiError && v.status === 409;
// Network/5xx/invalid receipts are ambiguous: the write may or may not have applied.
export const ambiguous = (v: unknown) => !(v instanceof ApiError) || v.status === 0 || v.status >= 500 || v.code === 'INVALID_RESPONSE';
