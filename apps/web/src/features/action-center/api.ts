import { ApiError, requestData } from '../../lib/api';

export type SourceType = 'CLASS_SESSION' | 'TASK' | 'NOTICE' | 'OPPORTUNITY_DEADLINE';
export type RecordSource = 'DEMO' | 'OFFICIAL_PUBLIC' | 'PLATFORM' | 'UNKNOWN';
export type SummaryItem = { source_type: SourceType; source_id: string; title: string; at: string; link: string; record_source: RecordSource };
export type Summary = { local_date: string; utc_offset: '+09:00'; window_start: string; window_end: string; classes: SummaryItem[]; tasks: SummaryItem[]; notices: SummaryItem[]; deadlines: SummaryItem[]; unread_notifications: number; unread_capped: boolean; ordering: 'TIME_ASC_DEMO'; priority_policy: 'NOT_DEFINED'; school_connection: 'NOT_CONNECTED' };
export type Notification = { id: string; source_type: SourceType; source_id: string; title: string; link: string; record_source: RecordSource; created_at: string; read_at: string | null; revision: number; delivery: 'IN_APP_ONLY' };
export type Page = { items: Notification[]; offset: number; limit: number; next_offset: number | null };

// Must equal the server's fixed section paths; any other link is treated as a tampered response.
export const LINKS: Record<SourceType, string> = { CLASS_SESSION: '/app/classrooms', TASK: '/app/classrooms', NOTICE: '/app/department', OPPORTUNITY_DEADLINE: '/app/opportunities' };
export const SOURCE_LABELS: Record<RecordSource, string> = { DEMO: '가상 시연 자료', OFFICIAL_PUBLIC: '공개 자료 인용', PLATFORM: '플랫폼 공지', UNKNOWN: '출처 미확인' };

type Obj = { [key: string]: unknown };
const object = (v: unknown): v is Obj => !!v && typeof v === 'object' && !Array.isArray(v);
const exact = (v: Obj, names: string[]) => Object.keys(v).length === names.length && names.every(n => Object.hasOwn(v, n));
const uuid = (v: unknown) => typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
const date = (v: unknown) => typeof v === 'string' && /(?:Z|[+-]\d\d:\d\d)$/.test(v) && Number.isFinite(Date.parse(v));
const title = (v: unknown) => typeof v === 'string' && v.length >= 1 && v.length <= 200;
const integer = (v: unknown, min: number) => Number.isSafeInteger(v) && (v as number) >= min;
const kind = (v: unknown): v is SourceType => typeof v === 'string' && Object.hasOwn(LINKS, v);
const source = (v: unknown) => typeof v === 'string' && Object.hasOwn(SOURCE_LABELS, v);
const linked = (v: Obj) => kind(v.source_type) && v.link === LINKS[v.source_type] && (v.source_type === 'NOTICE') === (v.record_source === 'PLATFORM');

function isItem(v: unknown, expected: SourceType): v is SummaryItem {
  return object(v) && exact(v, ['source_type', 'source_id', 'title', 'at', 'link', 'record_source'])
    && v.source_type === expected && uuid(v.source_id) && title(v.title) && date(v.at) && source(v.record_source) && linked(v);
}
const section = (v: unknown, expected: SourceType) => Array.isArray(v) && v.length <= 10 && v.every(i => isItem(i, expected));

export function isSummary(v: unknown): v is Summary {
  return object(v) && exact(v, ['local_date', 'utc_offset', 'window_start', 'window_end', 'classes', 'tasks', 'notices', 'deadlines', 'unread_notifications', 'unread_capped', 'ordering', 'priority_policy', 'school_connection'])
    && typeof v.local_date === 'string' && /^\d{4}-\d\d-\d\d$/.test(v.local_date) && v.utc_offset === '+09:00' && date(v.window_start) && date(v.window_end)
    && section(v.classes, 'CLASS_SESSION') && section(v.tasks, 'TASK') && section(v.notices, 'NOTICE') && section(v.deadlines, 'OPPORTUNITY_DEADLINE')
    && integer(v.unread_notifications, 0) && typeof v.unread_capped === 'boolean'
    && v.ordering === 'TIME_ASC_DEMO' && v.priority_policy === 'NOT_DEFINED' && v.school_connection === 'NOT_CONNECTED';
}
export function isNotification(v: unknown): v is Notification {
  return object(v) && exact(v, ['id', 'source_type', 'source_id', 'title', 'link', 'record_source', 'created_at', 'read_at', 'revision', 'delivery'])
    && uuid(v.id) && uuid(v.source_id) && title(v.title) && source(v.record_source) && linked(v) && date(v.created_at)
    && (v.read_at === null || date(v.read_at)) && integer(v.revision, 1) && v.delivery === 'IN_APP_ONLY';
}
export function isPage(v: unknown): v is Page {
  return object(v) && exact(v, ['items', 'offset', 'limit', 'next_offset']) && Array.isArray(v.items) && v.items.length <= 50 && v.items.every(isNotification)
    && integer(v.offset, 0) && integer(v.limit, 1) && (v.limit as number) <= 50 && (v.next_offset === null || integer(v.next_offset, (v.offset as number) + 1));
}

async function call<T>(path: string, guard: (v: unknown) => v is T, init: RequestInit): Promise<T> {
  const result = await requestData<unknown>('/action-center' + path, init);
  if (!guard(result)) throw new ApiError('INVALID_RESPONSE', 200);
  return result;
}
export const readSummary = (signal: AbortSignal) => call('/summary', isSummary, { signal });
export const readInbox = (offset: number, signal: AbortSignal) => call(`/notifications?offset=${offset}&limit=20`, isPage, { signal });
export async function markRead(item: Notification, signal: AbortSignal): Promise<Notification> {
  const row = await call(`/notifications/${item.id}/read`, isNotification, { method: 'POST', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_revision: item.revision }) });
  if (row.id !== item.id || row.read_at === null) throw new ApiError('INVALID_RESPONSE', 200);
  return row;
}
export const authFailure = (v: unknown) => v instanceof ApiError && [401, 403].includes(v.status);
export const conflict = (v: unknown) => v instanceof ApiError && v.status === 409;
