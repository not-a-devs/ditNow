import { ApiError, requestData } from '../../lib/api';

// Fixed fictional DEMO exercise kept in server process memory; not MariaDB, not official records.
export type CardKind = 'CLASS' | 'TASK' | 'NOTICE';
export type DemoCard = { id: string; kind: CardKind; title: string; detail: string; link: string; record_source: 'DEMO' };
export type DemoNotification = { id: string; card_id: string; title: string; link: string; read: boolean; revision: number; delivery: 'IN_APP_ONLY'; record_source: 'DEMO' };
export type DemoSummary = { mode: 'DEMO'; storage: 'PROCESS_MEMORY'; rule_based: true; ai_generated: false; school_connection: 'NOT_CONNECTED'; cards: DemoCard[]; notifications: DemoNotification[]; unread_count: number };
export type DemoReadResult = { notification: DemoNotification; already_read: boolean; unread_count: number };

// Must equal the server's fixed in-app paths; any other link is treated as a tampered response.
export const LINKS: Record<CardKind, string> = { CLASS: '/app/classrooms', TASK: '/app/classrooms', NOTICE: '/app/department' };
const CARD_IDS: Record<string, CardKind> = { 'demo-class-1': 'CLASS', 'demo-task-1': 'TASK', 'demo-notice-1': 'NOTICE' };
const BASE = '/me/demo-action-center';

type Obj = { [key: string]: unknown };
const object = (v: unknown): v is Obj => !!v && typeof v === 'object' && !Array.isArray(v);
const exact = (v: Obj, names: string[]) => Object.keys(v).length === names.length && names.every(n => Object.hasOwn(v, n));
const uuid = (v: unknown) => typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
const text = (v: unknown, max: number) => typeof v === 'string' && v.length >= 1 && Array.from(v).length <= max;
const integer = (v: unknown, min: number) => Number.isSafeInteger(v) && (v as number) >= min;

export function isCard(v: unknown): v is DemoCard {
  return object(v) && exact(v, ['id', 'kind', 'title', 'detail', 'link', 'record_source'])
    && typeof v.id === 'string' && Object.hasOwn(CARD_IDS, v.id) && CARD_IDS[v.id] === v.kind
    && text(v.title, 80) && text(v.detail, 160) && v.link === LINKS[v.kind as CardKind] && v.record_source === 'DEMO';
}
export function isNotification(v: unknown): v is DemoNotification {
  return object(v) && exact(v, ['id', 'card_id', 'title', 'link', 'read', 'revision', 'delivery', 'record_source'])
    && uuid(v.id) && typeof v.card_id === 'string' && Object.hasOwn(CARD_IDS, v.card_id) && v.link === LINKS[CARD_IDS[v.card_id]]
    && text(v.title, 80) && typeof v.read === 'boolean' && integer(v.revision, 1) && v.delivery === 'IN_APP_ONLY' && v.record_source === 'DEMO';
}
export function isSummary(v: unknown): v is DemoSummary {
  return object(v) && exact(v, ['mode', 'storage', 'rule_based', 'ai_generated', 'school_connection', 'cards', 'notifications', 'unread_count'])
    && v.mode === 'DEMO' && v.storage === 'PROCESS_MEMORY' && v.rule_based === true && v.ai_generated === false && v.school_connection === 'NOT_CONNECTED'
    && Array.isArray(v.cards) && v.cards.length <= 3 && v.cards.every(isCard)
    && Array.isArray(v.notifications) && v.notifications.length <= 3 && v.notifications.every(isNotification)
    && integer(v.unread_count, 0) && v.unread_count === v.notifications.filter(n => !(n as DemoNotification).read).length;
}
export function isReadResult(v: unknown): v is DemoReadResult {
  return object(v) && exact(v, ['notification', 'already_read', 'unread_count'])
    && isNotification(v.notification) && v.notification.read && typeof v.already_read === 'boolean' && integer(v.unread_count, 0) && (v.unread_count as number) <= 3;
}

async function call<T>(path: string, guard: (v: unknown) => v is T, init: RequestInit): Promise<T> {
  const result = await requestData<unknown>(BASE + path, init);
  if (!guard(result)) throw new ApiError('INVALID_RESPONSE', 200);
  return result;
}
export const readSummary = (signal: AbortSignal) => call('/summary', isSummary, { signal });
export async function markRead(item: DemoNotification, signal: AbortSignal): Promise<DemoReadResult> {
  const result = await call(`/notifications/${encodeURIComponent(item.id)}/read`, isReadResult, { method: 'POST', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ revision: item.revision }) });
  if (result.notification.id !== item.id || result.notification.card_id !== item.card_id
    || (result.already_read ? result.notification.revision < item.revision : result.notification.revision !== item.revision + 1))
    throw new ApiError('INVALID_RESPONSE', 200);
  return result;
}
export const authFailure = (v: unknown) => v instanceof ApiError && [401, 403].includes(v.status);
export const conflict = (v: unknown) => v instanceof ApiError && v.status === 409;
