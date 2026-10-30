import { ApiError, requestData } from '../../lib/api';

export type Purpose = 'study' | 'project' | 'social';
export type RequestedKind = 'FREE' | 'OFFICIAL';
export interface DemoChannelRequest {
  id: string; purpose: Purpose; requested_kind: RequestedKind; title: string;
  status: 'CREATED' | 'PENDING_REVIEW'; revision: number; created_at: string;
  official_badge: false; real_review: 'NOT_OPERATED'; record_source: 'DEMO'; persistence: 'PROCESS_MEMORY';
}
export interface DemoChannelList { items: DemoChannelRequest[]; per_user_limit: number; record_source: 'DEMO'; persistence: 'PROCESS_MEMORY' }
export interface DemoChannelCreate { purpose: Purpose; requested_kind: RequestedKind; consent: true }

const PATH = '/me/demo-channels';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const only = (value: Record<string, unknown>, keys: string[]) => Object.keys(value).every(key => keys.includes(key));
const int = (value: unknown, max = 1_000_000): value is number => Number.isInteger(value) && Number(value) >= 1 && Number(value) <= max;

export function isDemoChannelRequest(value: unknown): value is DemoChannelRequest {
  if (!object(value) || !only(value, ['id', 'purpose', 'requested_kind', 'title', 'status', 'revision', 'created_at', 'official_badge', 'real_review', 'record_source', 'persistence'])) return false;
  // OFFICIAL never becomes CREATED: there is no real review or approval in this demo.
  const statusOk = value.requested_kind === 'FREE' ? value.status === 'CREATED'
    : value.requested_kind === 'OFFICIAL' && value.status === 'PENDING_REVIEW';
  return typeof value.id === 'string' && UUID.test(value.id)
    && ['study', 'project', 'social'].includes(value.purpose as string) && statusOk
    && typeof value.title === 'string' && value.title.startsWith('[DEMO] ') && value.title.length <= 100
    && int(value.revision) && typeof value.created_at === 'string' && Number.isFinite(Date.parse(value.created_at))
    && value.official_badge === false && value.real_review === 'NOT_OPERATED'
    && value.record_source === 'DEMO' && value.persistence === 'PROCESS_MEMORY';
}
export function isDemoChannelList(value: unknown): value is DemoChannelList {
  return object(value) && only(value, ['items', 'per_user_limit', 'record_source', 'persistence'])
    && Array.isArray(value.items) && value.items.length <= 200 && value.items.every(isDemoChannelRequest)
    && int(value.per_user_limit, 200) && value.record_source === 'DEMO' && value.persistence === 'PROCESS_MEMORY';
}

export async function listDemoChannels(signal?: AbortSignal) {
  const data = await requestData<unknown>(PATH, { cache: 'no-store', signal });
  if (!isDemoChannelList(data)) throw new ApiError('INVALID_RESPONSE', 200);
  return data;
}
export async function createDemoChannel(body: DemoChannelCreate, signal?: AbortSignal) {
  const data = await requestData<unknown>(PATH, {
    method: 'POST', cache: 'no-store', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!isDemoChannelRequest(data)) throw new ApiError('INVALID_RESPONSE', 200);
  return data;
}
export async function cancelDemoChannel(request: Pick<DemoChannelRequest, 'id' | 'revision'>, signal?: AbortSignal) {
  if (!UUID.test(request.id) || !int(request.revision)) throw new ApiError('VALIDATION', 400);
  const data = await requestData<unknown>(`${PATH}/${request.id}?revision=${request.revision}`, { method: 'DELETE', cache: 'no-store', signal });
  if (!object(data) || data.id !== request.id || data.cancelled !== true) throw new ApiError('INVALID_RESPONSE', 200);
  return request.id;
}
