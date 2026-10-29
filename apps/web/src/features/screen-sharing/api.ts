import { ApiError, requestData } from '../../lib/api';

export interface Peer { peer_id: string; generation: number }
export interface Session { id: string; offering_id: string; state: 'READY' | 'LIVE' | 'ENDED'; revision: number; expires_at: string; is_presenter: boolean; me: Peer | null; presenter: Peer | null; viewers: Peer[]; audio: false; recording: false; media_provider: 'NOT_CONNECTED' }
export interface Context { offering_id: string; role: 'student' | 'teacher'; session: Session | null; source_kind: 'DEMO' }
export interface Signal { sequence: number; sender_peer_id: string; generation: number; kind: 'OFFER' | 'ANSWER' | 'ICE'; payload: string }
export interface Signals { items: Signal[]; cursor: number }
type Record = { [key: string]: unknown };
const object = (v: unknown): v is Record => !!v && typeof v === 'object' && !Array.isArray(v);
const exact = (v: Record, keys: string[]) => Object.keys(v).length === keys.length && keys.every(k => Object.hasOwn(v, k));
export const uuid = (v: unknown): v is string => typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
const integer = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) >= 1;
const peer = (v: unknown): v is Peer => object(v) && exact(v, ['peer_id','generation']) && uuid(v.peer_id) && integer(v.generation);
function videoPayload(kind: unknown, payload: unknown): payload is string {
  if (typeof payload !== 'string' || !payload || payload.includes('\0') || new TextEncoder().encode(payload).length > (kind === 'ICE' ? 2048 : 65536)) return false;
  if (kind === 'ICE') return payload.startsWith('candidate:') && !/[\r\n]/.test(payload);
  const lines = payload.replaceAll('\r\n', '\n').split('\n');
  const media = lines.filter(line => line.startsWith('m='));
  const directions = lines.filter(line => /^a=(sendonly|recvonly|sendrecv|inactive)$/.test(line));
  const expected = kind === 'OFFER' ? 'a=sendonly' : 'a=recvonly';
  return lines[0] === 'v=0' && media.length === 1 && media[0].startsWith('m=video ') && directions.length > 0 && directions.every(line => [expected, 'a=inactive'].includes(line));
}
export function isSession(v: unknown): v is Session {
  return object(v) && exact(v, ['id','offering_id','state','revision','expires_at','is_presenter','me','presenter','viewers','audio','recording','media_provider'])
    && uuid(v.id) && uuid(v.offering_id) && ['READY','LIVE','ENDED'].includes(String(v.state)) && integer(v.revision)
    && typeof v.expires_at === 'string' && /(?:Z|[+-]\d\d:\d\d)$/.test(v.expires_at) && Number.isFinite(Date.parse(v.expires_at))
    && typeof v.is_presenter === 'boolean' && (v.me === null || peer(v.me)) && (v.presenter === null || peer(v.presenter))
    && Array.isArray(v.viewers) && v.viewers.length <= 50 && v.viewers.every(peer)
    && (!v.is_presenter ? v.viewers.length === 0 : true) && v.audio === false && v.recording === false && v.media_provider === 'NOT_CONNECTED';
}
export function isContext(v: unknown): v is Context {
  return object(v) && exact(v, ['offering_id','role','session','source_kind']) && uuid(v.offering_id)
    && ['student','teacher'].includes(String(v.role)) && v.source_kind === 'DEMO' && (v.session === null || isSession(v.session));
}
export function isSignals(v: unknown): v is Signals {
  return object(v) && exact(v, ['items','cursor']) && Number.isSafeInteger(v.cursor) && Number(v.cursor) >= 0
    && Array.isArray(v.items) && v.items.length <= 50 && v.items.every(s => object(s) && exact(s, ['sequence','sender_peer_id','generation','kind','payload'])
      && integer(s.sequence) && s.sequence <= Number(v.cursor) && uuid(s.sender_peer_id) && integer(s.generation)
      && ['OFFER','ANSWER','ICE'].includes(String(s.kind)) && videoPayload(s.kind, s.payload));
}
export async function read<T>(path: string, guard: (v: unknown) => v is T, signal: AbortSignal): Promise<T> {
  const value = await requestData<unknown>('/screen-sharing' + path, { signal });
  if (!guard(value)) throw new ApiError('INVALID_RESPONSE', 200);
  return value;
}
export async function mutate<T>(path: string, body: object | null, guard: (v: unknown) => v is T, signal: AbortSignal, key?: string): Promise<T> {
  const value = await requestData<unknown>('/screen-sharing' + path, { method: 'POST', signal,
    headers: { 'Content-Type': 'application/json', ...(key ? { 'Idempotency-Key': key } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) });
  if (!guard(value)) throw new ApiError('INVALID_RESPONSE', 200);
  return value;
}
export const noContent = (v: unknown): v is null => v === null;
export const sequence = (v: unknown): v is number => integer(v);
export const safeMessage = '화면 공유 연결을 확인하지 못했습니다. 캡처를 중지했습니다. 현재 분반 권한과 연결 상태를 다시 확인하세요.';
