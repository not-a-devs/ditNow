// Feature paths only: the shared requestData adds the /api/v1 base. Never prepend it here.
import { ApiError, requestData } from '../../lib/api';
import {
  isAttOfferings, isCorrection, isCorrections, isEnrollment, isEnrollments, isMyAttendance, isOffering, isOfferings, isPolicy,
  isRecord, isRecords, isRequest, isRequests, isSession, isSessions, isTranscript,
  type FinalMark, type RequestKind,
} from './models';

const seg = (id: string) => encodeURIComponent(id);
const att = (offeringId: string) => `/academics/attendance/offerings/${seg(offeringId)}`;

async function get<T>(path: string, guard: (v: unknown) => v is T, signal?: AbortSignal): Promise<T> {
  const data = await requestData<unknown>(path, { signal });
  if (!guard(data)) throw new ApiError('INVALID_RESPONSE', 200);
  return data;
}
async function send<T>(path: string, body: object, guard: (v: unknown) => v is T, opts: { method?: string; key?: string; signal?: AbortSignal } = {}): Promise<T> {
  const data = await requestData<unknown>(path, {
    method: opts.method ?? 'POST', body: JSON.stringify(body), signal: opts.signal,
    headers: { 'Content-Type': 'application/json', ...(opts.key ? { 'Idempotency-Key': opts.key } : {}) },
  });
  if (!guard(data)) throw new ApiError('INVALID_RESPONSE', 200);
  return data;
}

export const api = {
  policy: (signal?: AbortSignal) => get('/academics/policy', isPolicy, signal),
  offerings: (q: string, termId?: string, signal?: AbortSignal) => {
    const params = new URLSearchParams({ q, limit: '25' });
    if (termId) params.set('term_id', termId);
    return get(`/academics/offerings?${params}`, isOfferings, signal);
  },
  offering: (id: string, signal?: AbortSignal) => get(`/academics/offerings/${seg(id)}`, isOffering, signal),
  enrollments: (signal?: AbortSignal) => get('/academics/enrollments', isEnrollments, signal),
  enroll: (offeringId: string, key: string) => send('/academics/enrollments', { offering_id: offeringId }, isEnrollment, { key }),
  drop: (id: string, revision: number) => send(`/academics/enrollments/${seg(id)}/drop`, { expected_revision: revision }, isEnrollment),
  transcript: (signal?: AbortSignal) => get('/academics/records', isTranscript, signal),
  requests: (signal?: AbortSignal) => get('/academics/requests', isRequests, signal),
  createRequest: (body: { kind: RequestKind; reason: string } & Record<string, string | null>, key: string) => send('/academics/requests', body, isRequest, { key }),
  submitRequest: (id: string, revision: number) => send(`/academics/requests/${seg(id)}/submit`, { expected_revision: revision }, isRequest),
  withdrawRequest: (id: string, revision: number) => send(`/academics/requests/${seg(id)}/withdraw`, { expected_revision: revision }, isRequest),
  attendanceOfferings: (signal?: AbortSignal) => get('/academics/attendance/offerings', isAttOfferings, signal),
  sessions: (offeringId: string, signal?: AbortSignal) => get(`${att(offeringId)}/sessions`, isSessions, signal),
  openSession: (offeringId: string, label: string, key: string) => send(`${att(offeringId)}/sessions`, { label }, isSession, { key }),
  closeSession: (offeringId: string, sessionId: string, revision: number) => send(`${att(offeringId)}/sessions/${seg(sessionId)}/close`, { expected_revision: revision }, isSession),
  checkIn: (offeringId: string, sessionId: string, code: string) => send(`${att(offeringId)}/sessions/${seg(sessionId)}/check-in`, { method: 'DEMO_CODE', code }, isRecord),
  records: (offeringId: string, sessionId: string, signal?: AbortSignal) => get(`${att(offeringId)}/sessions/${seg(sessionId)}/records`, isRecords, signal),
  mark: (offeringId: string, sessionId: string, memberRef: string, mark: FinalMark, reason: string, revision: number) =>
    send(`${att(offeringId)}/sessions/${seg(sessionId)}/records/${seg(memberRef)}`, { mark, reason, expected_revision: revision }, isRecord, { method: 'PUT' }),
  myAttendance: (offeringId: string, signal?: AbortSignal) => get(`${att(offeringId)}/me`, isMyAttendance, signal),
  requestCorrection: (offeringId: string, recordId: string, requestedMark: FinalMark, reason: string, key: string) =>
    send(`${att(offeringId)}/records/${seg(recordId)}/corrections`, { requested_mark: requestedMark, reason }, isCorrection, { key }),
  corrections: (offeringId: string, signal?: AbortSignal) => get(`${att(offeringId)}/corrections`, isCorrections, signal),
  resolveCorrection: (offeringId: string, id: string, decision: 'ACCEPTED' | 'REJECTED', reason: string, revision: number) =>
    send(`${att(offeringId)}/corrections/${seg(id)}/resolve`, { decision, reason, expected_revision: revision }, isCorrection),
};

/** Same intent (identical payload) reuses its key; any input change rotates to a new key. */
export interface Intent { fingerprint: string; key: string }
export function intentFor(previous: Intent | null, payload: object, make: () => string = () => crypto.randomUUID()): Intent {
  const fingerprint = JSON.stringify(payload);
  return previous && previous.fingerprint === fingerprint ? previous : { fingerprint, key: make() };
}

export const isAuthFailure = (error: unknown) => error instanceof ApiError && (error.status === 401 || error.status === 403);
export function messageOf(error: unknown): string {
  if (error instanceof ApiError && error.status === 503) return '승인된 공통 인증·학사 저장소·시연 정책이 연결되지 않았습니다. 가상 로그인으로 대체하지 않습니다.';
  if (error instanceof ApiError && error.code === 'INVALID_RESPONSE') return '서버 응답 형식을 확인하지 못했습니다. 저장 여부를 목록에서 다시 확인해 주세요.';
  return error instanceof ApiError ? error.message : '요청을 처리하지 못했습니다. 다시 시도해 주세요.';
}
