import { ApiError, requestData } from '../../lib/api';

// requestData adds the /api/v1 base; feature paths carry the module prefix exactly once.
const PREFIX = '/notice-acknowledgements';
export const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

interface Demo { record_source: 'DEMO'; storage: 'PROCESS_MEMORY'; official_effect: false; restart_reset: true }
export interface RequestView extends Demo { notice_id: string; request_revision: number }
export interface OwnState extends Demo {
  notice_id: string; requested: boolean; request_revision: number | null; can_request: boolean; can_acknowledge: boolean;
  acknowledged: boolean; acknowledged_at: string | null; can_view_summary: boolean;
}
export interface AckReceipt extends Demo { notice_id: string; request_revision: number; acknowledged: true; acknowledged_at: string }
export interface AckSummary extends Demo {
  notice_id: string; request_revision: number; eligible_total: number; acknowledged_count: number; audience_basis: 'TRUSTED_PORT_CURRENT';
}

type Rec = Record<string, unknown>;
const isRec = (v: unknown): v is Rec => typeof v === 'object' && v !== null && !Array.isArray(v);
const isCount = (v: unknown): v is number => Number.isSafeInteger(v) && (v as number) >= 0;
const isRevision = (v: unknown): v is number => Number.isSafeInteger(v) && (v as number) >= 1;
const isTime = (v: unknown): v is string => typeof v === 'string' && !Number.isNaN(Date.parse(v));
const exactKeys = (v: Rec, keys: string[]) => Object.keys(v).length === keys.length && keys.every(k => k in v);
const DEMO_KEYS = ['record_source', 'storage', 'official_effect', 'restart_reset'];
const isDemo = (v: Rec) => v.record_source === 'DEMO' && v.storage === 'PROCESS_MEMORY' && v.official_effect === false && v.restart_reset === true;

export function isRequestView(v: unknown, noticeId: string): v is RequestView {
  return isRec(v) && exactKeys(v, [...DEMO_KEYS, 'notice_id', 'request_revision']) && isDemo(v)
    && v.notice_id === noticeId && isRevision(v.request_revision);
}
export function isOwnState(v: unknown, noticeId: string): v is OwnState {
  if (!isRec(v) || !exactKeys(v, [...DEMO_KEYS, 'notice_id', 'requested', 'request_revision', 'can_request', 'can_acknowledge', 'acknowledged', 'acknowledged_at', 'can_view_summary'])) return false;
  if (!isDemo(v) || v.notice_id !== noticeId) return false;
  if (typeof v.requested !== 'boolean' || typeof v.can_request !== 'boolean' || typeof v.can_acknowledge !== 'boolean' || typeof v.acknowledged !== 'boolean' || typeof v.can_view_summary !== 'boolean') return false;
  if (v.requested ? !isRevision(v.request_revision) : v.request_revision !== null) return false;
  return v.acknowledged ? isTime(v.acknowledged_at) && v.requested : v.acknowledged_at === null;
}
export function isAckReceipt(v: unknown, noticeId: string): v is AckReceipt {
  return isRec(v) && exactKeys(v, [...DEMO_KEYS, 'notice_id', 'request_revision', 'acknowledged', 'acknowledged_at']) && isDemo(v)
    && v.notice_id === noticeId && isRevision(v.request_revision) && v.acknowledged === true && isTime(v.acknowledged_at);
}
export function isAckSummary(v: unknown, noticeId: string): v is AckSummary {
  return isRec(v) && exactKeys(v, [...DEMO_KEYS, 'notice_id', 'request_revision', 'eligible_total', 'acknowledged_count', 'audience_basis']) && isDemo(v)
    && v.notice_id === noticeId && isRevision(v.request_revision) && isCount(v.eligible_total) && isCount(v.acknowledged_count)
    && (v.acknowledged_count as number) <= (v.eligible_total as number) && v.audience_basis === 'TRUSTED_PORT_CURRENT';
}

function checked<T>(value: unknown, guard: (v: unknown, id: string) => v is T, noticeId: string): T {
  if (!guard(value, noticeId)) throw new ApiError('INVALID_RESPONSE', 0);
  return value;
}
const post = (body: unknown, key: string, signal: AbortSignal): RequestInit => ({
  method: 'POST', signal, body: JSON.stringify(body),
  headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
});

export async function fetchOwnState(noticeId: string, signal: AbortSignal) {
  return checked(await requestData<unknown>(`${PREFIX}/${noticeId}`, { signal }), isOwnState, noticeId);
}
export async function fetchSummary(noticeId: string, signal: AbortSignal) {
  return checked(await requestData<unknown>(`${PREFIX}/${noticeId}/summary`, { signal }), isAckSummary, noticeId);
}
export async function sendAckRequest(noticeId: string, key: string, signal: AbortSignal) {
  const value = await requestData<unknown>(`${PREFIX}/request`, post({ notice_id: noticeId, opt_in: true }, key, signal));
  return checked(value, isRequestView, noticeId);
}
export async function sendAck(noticeId: string, requestRevision: number, key: string, signal: AbortSignal) {
  const value = await requestData<unknown>(`${PREFIX}/${noticeId}/ack`, post({ request_revision: requestRevision }, key, signal));
  return checked(value, isAckReceipt, noticeId);
}
export function newIntentKey() {
  return `ack-${crypto.randomUUID()}`;
}
