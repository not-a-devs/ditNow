// Uses the real shared requestData with a stubbed fetch so the final browser URL is asserted.
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../lib/api';
import { api, intentFor, isAuthFailure, messageOf } from './api';
import { isEnrollment, isMyAttendance, isOffering, isPolicy, isRecord, isRequest, isTranscript, officialLink } from './models';

const O = '11111111-1111-4111-8111-111111111111';
const S = '22222222-2222-4222-8222-222222222222';
const R = '33333333-3333-4333-8333-333333333333';

function stub(data: unknown, status = 200) {
  const fetch = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify(status < 400 ? { data } : data), { status }));
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
const urlOf = (fetch: ReturnType<typeof stub>) => String(fetch.mock.calls[0][0]);
const offering = {
  id: O, term_id: S, course_code: 'DEMO-1', title: '가상 자료구조', section: 'A', instructor_name: '가상 교수', credits: 3, capacity: 2,
  enrolled_count: 0, meetings: [{ weekday: 1, starts_minute: 540, ends_minute: 630 }], syllabus_summary: '요약',
  syllabus_source: { source_kind: 'DEMO', source_url: null, checked_at: null }, record_source: 'DEMO',
};

describe('academics paths through the shared client', () => {
  const origin = window.location.origin;
  it.each([
    ['policy', () => api.policy(), '/api/v1/academics/policy'],
    ['offerings', () => api.offerings('자료', S), `/api/v1/academics/offerings?q=%EC%9E%90%EB%A3%8C&limit=25&term_id=${S}`],
    ['offering', () => api.offering(O), `/api/v1/academics/offerings/${O}`],
    ['enrollments', () => api.enrollments(), '/api/v1/academics/enrollments'],
    ['records', () => api.transcript(), '/api/v1/academics/records'],
    ['requests', () => api.requests(), '/api/v1/academics/requests'],
    ['att offerings', () => api.attendanceOfferings(), '/api/v1/academics/attendance/offerings'],
    ['sessions', () => api.sessions(O), `/api/v1/academics/attendance/offerings/${O}/sessions`],
    ['records of session', () => api.records(O, S), `/api/v1/academics/attendance/offerings/${O}/sessions/${S}/records`],
    ['me', () => api.myAttendance(O), `/api/v1/academics/attendance/offerings/${O}/me`],
    ['corrections', () => api.corrections(O), `/api/v1/academics/attendance/offerings/${O}/corrections`],
  ])('%s has exactly one /api/v1 prefix', async (_name, call, path) => {
    const fetch = stub(null);
    await call().catch(() => undefined);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(urlOf(fetch)).toBe(`${origin}${path}`);
    expect(urlOf(fetch)).not.toContain('/api/v1/api/v1');
  });

  it('sends idempotent create with the key header and no actor fields', async () => {
    const fetch = stub({ id: R, offering_id: O, term_id: S, status: 'ENROLLED', enrolled_at: '2026-10-30T00:00:00Z', dropped_at: null, revision: 1, record_source: 'DEMO' });
    const row = await api.enroll(O, 'key-aaaaaaaaaaaaaaaa');
    expect(row.status).toBe('ENROLLED');
    expect(urlOf(fetch)).toBe(`${origin}/api/v1/academics/enrollments`);
    const init = fetch.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(init.credentials).toBe('same-origin');
    expect((init.headers as Record<string, string>)['Idempotency-Key']).toBe('key-aaaaaaaaaaaaaaaa');
    expect(JSON.parse(String(init.body))).toEqual({ offering_id: O });
  });

  it('marks with PUT and check-in only with the demo code method', async () => {
    const fetch = stub(null);
    await api.mark(O, S, R, 'LATE', '사유', 2).catch(() => undefined);
    expect(urlOf(fetch)).toBe(`${origin}/api/v1/academics/attendance/offerings/${O}/sessions/${S}/records/${R}`);
    expect((fetch.mock.calls[0][1] as RequestInit).method).toBe('PUT');
    const check = stub(null);
    await api.checkIn(O, S, '123456').catch(() => undefined);
    expect(JSON.parse(String((check.mock.calls[0][1] as RequestInit).body))).toEqual({ method: 'DEMO_CODE', code: '123456' });
  });

  it.each(['../policy', 'a/../../b', 'x?y=1#z'])('encodes ids so they cannot leave the feature path: %s', async id => {
    const fetch = stub(null);
    await api.offering(id).catch((error: unknown) => expect(error).toBeInstanceOf(ApiError));
    for (const call of fetch.mock.calls) {
      const url = new URL(String(call[0]));
      expect(url.pathname.startsWith('/api/v1/academics/offerings/')).toBe(true);
      expect(url.search).toBe('');
    }
  });

  it('rejects a success body that fails the runtime guard', async () => {
    stub({ ...offering, student_id: 'private' });
    await expect(api.offering(O)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  });

  it('surfaces server errors with code, status and request id', async () => {
    stub({ code: 'FORBIDDEN', message: 'x', request_id: '44444444-4444-4444-8444-444444444444' }, 403);
    const error = await api.enrollments().catch((e: unknown) => e);
    expect(error).toMatchObject({ code: 'FORBIDDEN', status: 403, requestId: '44444444-4444-4444-8444-444444444444' });
    expect(isAuthFailure(error)).toBe(true);
    expect(messageOf(new ApiError('UNAVAILABLE', 503))).toContain('시연 정책');
  });
});

describe('intent keys', () => {
  let n = 0;
  const make = () => `key-${++n}`;
  it('reuses the key for the identical payload and rotates on change', () => {
    const first = intentFor(null, { a: 1 }, make);
    expect(intentFor(first, { a: 1 }, make)).toBe(first);
    const changed = intentFor(first, { a: 2 }, make);
    expect(changed.key).not.toBe(first.key);
  });
});

describe('runtime guards', () => {
  it('accepts demo offering and rejects private or uncited official fields', () => {
    expect(isOffering(offering)).toBe(true);
    expect(isOffering({ ...offering, syllabus_source: { source_kind: 'OFFICIAL_PUBLIC', source_url: 'https://www.dit.ac.kr/', checked_at: null } })).toBe(false);
    expect(isOffering({ ...offering, syllabus_source: { source_kind: 'DEMO', source_url: 'https://www.dit.ac.kr/', checked_at: null } })).toBe(false);
    expect(isOffering({ ...offering, syllabus_source: { source_kind: 'OFFICIAL_PUBLIC', source_url: 'javascript:alert(1)', checked_at: '2026-10-29T00:00:00Z' } })).toBe(false);
    expect(officialLink({ source_kind: 'OFFICIAL_PUBLIC', source_url: 'https://www.dit.ac.kr/kr/index.php?pCode=classreginfo', checked_at: '2026-10-29T00:00:00Z' })?.url)
      .toBe('https://www.dit.ac.kr/kr/index.php?pCode=classreginfo');
    expect(officialLink({ source_kind: 'UNKNOWN', source_url: null, checked_at: null })).toBeNull();
  });
  it('rejects official-effect or graduation claims and private identifiers', () => {
    expect(isTranscript({ grades: [], listed_credit_total: 0, graduation_judgement: 'GRADUATED', official_effect: 'NONE', record_source: 'DEMO' })).toBe(false);
    const request = { id: R, kind: 'READMISSION', status: 'DRAFT', target_term_id: S, target_department_id: null, target_grade_id: null, reason: 'r', created_at: '2026-10-30T00:00:00Z', updated_at: '2026-10-30T00:00:00Z', submitted_at: null, withdrawn_at: null, revision: 1, review_state: 'NOT_CONNECTED', official_effect: 'NONE', record_source: 'DEMO' };
    expect(isRequest(request)).toBe(true);
    expect(isRequest({ ...request, review_state: 'APPROVED' })).toBe(false);
    expect(isRequest({ ...request, student_id: R })).toBe(false);
    expect(isEnrollment({ id: R })).toBe(false);
    const record = { id: R, session_id: S, member_ref: null, student_label: null, mark: 'PRESENT', checked_in_at: null, updated_at: null, revision: 1, is_mine: true, judgement: 'DEMO_DISPLAY_ONLY' };
    expect(isRecord(record)).toBe(true);
    expect(isRecord({ ...record, judgement: 'OFFICIAL' })).toBe(false);
    const session = { id: S, offering_id: O, label: 's', status: 'OPEN', opened_at: '2026-10-30T00:00:00Z', check_in_closes_at: '2026-10-30T00:10:00Z', closed_at: null, revision: 1, check_in_code: '123456', record_source: 'DEMO' };
    expect(isMyAttendance({ sessions: [session], records: [], corrections: [], record_source: 'DEMO' })).toBe(false);
    expect(isPolicy({ policy_id: 'p', label: 'DEMO', registration_windows: {}, request_windows: {}, max_credits_per_term: 6, check_in_window_minutes: 10, check_in_attempt_limit: 3, policy_source: 'DEMO', school_rules: 'CONNECTED', blocked: [] })).toBe(false);
  });
});
