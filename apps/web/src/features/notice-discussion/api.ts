import { ApiError, requestData } from '../../lib/api';

export type Item = { id: string; department_id: string; kind: 'QUESTION' | 'COMMENT'; question_id: string | null; title: string | null; body: string; revision: number; created_at: string; updated_at: string; is_mine: boolean; record_source: 'DEMO'; identity_display_policy: 'BLOCKED' };
export type Summary = { id: string; title: string; status: 'PUBLISHED' | 'ARCHIVED'; revision: number };
export type Notice = Omit<Summary, 'status'> & { status: 'DRAFT' | 'PUBLISHED' | 'ARCHIVED'; body: string; updated_at: string; school_connection: 'NOT_CONNECTED'; attachments: { id: string; filename: string; size_bytes: number; storage: 'NOT_CONNECTED' }[]; history: { revision: number; changed_at: string; event: string }[] };
export type Page = { items: Item[]; offset: number; limit: number };
type Record = { [key: string]: unknown };
const object = (v: unknown): v is Record => !!v && typeof v === 'object' && !Array.isArray(v);
const exact = (v: Record, names: string[]) => Object.keys(v).length === names.length && names.every(n => Object.hasOwn(v, n));
const text = (v: unknown, max: number): v is string => typeof v === 'string' && v.length <= max;
const integer = (v: unknown, min = 1): v is number => Number.isSafeInteger(v) && (v as number) >= min;
export const uuid = (v: unknown): v is string => typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
const date = (v: unknown) => typeof v === 'string' && /(?:Z|[+-]\d\d:\d\d)$/.test(v) && Number.isFinite(Date.parse(v));
const strings = (v: unknown, allowed: string[]) => typeof v === 'string' && allowed.includes(v);
export function isItem(v: unknown): v is Item {
  return object(v) && exact(v, ['id','department_id','kind','question_id','title','body','revision','created_at','updated_at','is_mine','record_source','identity_display_policy'])
    && uuid(v.id) && uuid(v.department_id) && strings(v.kind, ['QUESTION','COMMENT'])
    && (v.kind === 'QUESTION' ? v.question_id === null && text(v.title, 160) : uuid(v.question_id) && v.title === null)
    && text(v.body, 4000) && integer(v.revision) && date(v.created_at) && date(v.updated_at)
    && typeof v.is_mine === 'boolean' && v.record_source === 'DEMO' && v.identity_display_policy === 'BLOCKED';
}
export function isPage(v: unknown): v is Page {
  return object(v) && exact(v, ['items','offset','limit']) && Array.isArray(v.items) && v.items.length <= 50 && v.items.every(isItem) && integer(v.offset, 0) && integer(v.limit) && v.limit <= 50;
}
export function isSummaries(v: unknown): v is Summary[] {
  return Array.isArray(v) && v.length <= 50 && v.every(r => object(r) && exact(r, ['id','title','status','revision']) && uuid(r.id) && text(r.title, 500) && strings(r.status, ['PUBLISHED','ARCHIVED']) && integer(r.revision));
}
export function isNotice(v: unknown): v is Notice {
  return object(v) && exact(v, ['id','title','body','status','revision','updated_at','attachments','history','school_connection'])
    && uuid(v.id) && text(v.title, 500) && text(v.body, 20000) && strings(v.status, ['DRAFT','PUBLISHED','ARCHIVED']) && integer(v.revision) && date(v.updated_at) && v.school_connection === 'NOT_CONNECTED'
    && Array.isArray(v.attachments) && v.attachments.length <= 100 && v.attachments.every(a => object(a) && exact(a, ['id','filename','size_bytes','storage']) && uuid(a.id) && text(a.filename, 180) && !/[\x00-\x1f/\\:]/.test(a.filename) && integer(a.size_bytes, 0) && a.size_bytes <= 100000000 && a.storage === 'NOT_CONNECTED')
    && Array.isArray(v.history) && v.history.length <= 100 && v.history.every(h => object(h) && exact(h, ['revision','changed_at','event']) && integer(h.revision) && h.revision <= (v.revision as number) && date(h.changed_at) && strings(h.event, ['CREATED','CONTENT_REVISED','PUBLISHED','ARCHIVED']));
}
export async function read<T>(path: string, guard: (v: unknown) => v is T, signal: AbortSignal): Promise<T> {
  const result = await requestData<unknown>('/notice-discussion' + path, { signal });
  if (!guard(result)) throw new ApiError('INVALID_RESPONSE', 200);
  return result;
}
export async function write(path: string, method: string, body: object | null, key: string | null, signal: AbortSignal): Promise<Item | null> {
  const result = await requestData<unknown>('/notice-discussion' + path, { method, signal, headers: { 'Content-Type': 'application/json', ...(key ? { 'Idempotency-Key': key } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) });
  if (method === 'DELETE' ? result !== null : !isItem(result)) throw new ApiError('INVALID_RESPONSE', 200);
  return result as Item | null;
}
export const authFailure = (v: unknown) => v instanceof ApiError && [401,403].includes(v.status);
export const safeError = () => '공통 인증·학과 권한·저장소 연결 또는 현재 상태를 확인해 주세요. 저장 여부가 불확실하면 같은 입력으로 다시 시도하세요.';
