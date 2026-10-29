import { StrictMode } from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, requestData } from '../../lib/api';
import AcademicsPage from './index';

vi.mock('../../lib/api', async importOriginal => ({ ...await importOriginal<typeof import('../../lib/api')>(), requestData: vi.fn() }));

const O = '11111111-1111-4111-8111-111111111111';
const T = '22222222-2222-4222-8222-222222222222';
const E = '33333333-3333-4333-8333-333333333333';
const S = '44444444-4444-4444-8444-444444444444';
const AT = '2026-10-30T00:00:00Z';
const policy = { policy_id: 'p', label: 'DEMO 시연 정책', registration_windows: { [T]: { opens_at: AT, closes_at: '2026-10-31T00:00:00Z' } }, request_windows: {}, max_credits_per_term: 6, check_in_window_minutes: 10, check_in_attempt_limit: 3, policy_source: 'DEMO', school_rules: 'NOT_CONNECTED', blocked: ['BLUETOOTH_IDENTITY_CHECK'] };
const offering = { id: O, term_id: T, course_code: 'DEMO-1', title: '가상 자료구조', section: 'A', instructor_name: '가상 교수', credits: 3, capacity: 2, enrolled_count: 0, meetings: [], syllabus_summary: '요약', syllabus_source: { source_kind: 'DEMO', source_url: null, checked_at: null }, record_source: 'DEMO' };
const enrollment = { id: E, offering_id: O, term_id: T, status: 'ENROLLED', enrolled_at: AT, dropped_at: null, revision: 1, record_source: 'DEMO' };
const request = { id: E, kind: 'LEAVE_OF_ABSENCE', status: 'DRAFT', target_term_id: T, target_department_id: null, target_grade_id: null, reason: '가상 사유', created_at: AT, updated_at: AT, submitted_at: null, withdrawn_at: null, revision: 1, review_state: 'NOT_CONNECTED', official_effect: 'NONE', record_source: 'DEMO' };
const session = { id: S, offering_id: O, label: '1주차', status: 'OPEN', opened_at: AT, check_in_closes_at: '2026-10-30T00:10:00Z', closed_at: null, revision: 1, check_in_code: null, record_source: 'DEMO' };

type Handler = (init?: RequestInit) => unknown;
let routes: Record<string, Handler>;
const calls = () => vi.mocked(requestData).mock.calls;
const callsTo = (path: string) => calls().filter(([p]) => p === path);
const keyOf = (init?: RequestInit) => (init?.headers as Record<string, string> | undefined)?.['Idempotency-Key'];

beforeEach(() => {
  routes = {
    '/academics/policy': () => policy,
    '/academics/offerings?q=&limit=25': () => [offering],
    '/academics/enrollments': init => init?.method === 'POST' ? enrollment : [],
    '/academics/records': () => ({ grades: [], listed_credit_total: 0, graduation_judgement: 'NOT_PROVIDED', official_effect: 'NONE', record_source: 'DEMO' }),
    '/academics/requests': () => [],
    '/academics/attendance/offerings': () => [{ offering_id: O, title: '가상 자료구조', role: 'student', record_source: 'DEMO' }],
  };
  vi.mocked(requestData).mockReset();
  vi.mocked(requestData).mockImplementation(async (path: string, init?: RequestInit) => {
    const handler = routes[path];
    if (!handler) throw new ApiError('NOT_FOUND', 404);
    const value = handler(init);
    if (value instanceof Error) throw value;
    return value;
  });
});

describe('academics first-pass screen', () => {
  it('fails closed with a retry when the common provider is missing', async () => {
    vi.mocked(requestData).mockImplementation(async () => { throw new ApiError('UNAVAILABLE', 503); });
    render(<AcademicsPage />);
    const alerts = await screen.findAllByRole('alert');
    expect(alerts[0]).toHaveTextContent('공통 인증·학사 저장소·시연 정책');
    expect(screen.getAllByRole('button', { name: '다시 시도' }).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: '시연 수강 신청' })).not.toBeInTheDocument();
  });

  it('shows the injected demo policy separately from school rules', async () => {
    render(<AcademicsPage />);
    const banner = await screen.findByLabelText('시연 정책');
    expect(banner).toHaveTextContent('DEMO 시연 정책');
    expect(banner).toHaveTextContent('NOT_CONNECTED');
    expect(banner).toHaveTextContent('블루투스 신원 확인');
  });

  it('reuses the same key after an uncertain failure and shows success only after a valid response', async () => {
    let attempt = 0;
    routes['/academics/enrollments'] = init => init?.method === 'POST' ? (++attempt === 1 ? new ApiError('NETWORK', 0) : enrollment) : [];
    render(<AcademicsPage />);
    fireEvent.click(await screen.findByRole('button', { name: '시연 수강 신청' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('서버에 연결하지 못했습니다');
    expect(screen.queryByText(/시연 수강 신청이 저장되었습니다/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '시연 수강 신청' }));
    expect(await screen.findByText(/시연 수강 신청이 저장되었습니다/)).toBeInTheDocument();
    const posts = callsTo('/academics/enrollments').filter(([, init]) => init?.method === 'POST');
    expect(posts).toHaveLength(2);
    expect(keyOf(posts[0][1])).toBe(keyOf(posts[1][1]));
    expect(JSON.parse(String(posts[0][1]?.body))).toEqual({ offering_id: O });
  });

  it('does not show success when the response fails the runtime guard', async () => {
    routes['/academics/enrollments'] = init => init?.method === 'POST' ? { ...enrollment, student_id: 'private' } : [];
    render(<AcademicsPage />);
    fireEvent.click(await screen.findByRole('button', { name: '시연 수강 신청' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('서버 응답 형식');
    expect(screen.queryByText(/저장되었습니다/)).not.toBeInTheDocument();
  });

  it.each([401, 403])('clears personal screens and keeps the parent error on %i', async status => {
    routes['/academics/enrollments'] = init => init?.method === 'POST' ? new ApiError(status === 401 ? 'UNAUTHORIZED' : 'FORBIDDEN', status) : [];
    render(<AcademicsPage />);
    fireEvent.click(await screen.findByRole('button', { name: '시연 수강 신청' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(status === 401 ? '로그인이 필요한' : '접근할 권한');
    expect(alert).toHaveTextContent('개인 학사·출결 화면을 비웠습니다');
    expect(screen.queryByText('가상 자료구조')).not.toBeInTheDocument();
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
    fireEvent.click(within(alert).getByRole('button', { name: '다시 확인' }));
    expect(await screen.findByRole('tablist')).toBeInTheDocument();
  });

  it('finishes a mutation under StrictMode like main.tsx', async () => {
    render(<StrictMode><AcademicsPage /></StrictMode>);
    fireEvent.click(await screen.findByRole('button', { name: '시연 수강 신청' }));
    expect(await screen.findByText(/시연 수강 신청이 저장되었습니다/)).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: '신청됨' })).toBeInTheDocument();
  });

  it.each([401, 403])('forwards %i from a mutation to the parent under StrictMode', async status => {
    routes['/academics/enrollments'] = init => init?.method === 'POST' ? new ApiError(status === 401 ? 'UNAUTHORIZED' : 'FORBIDDEN', status) : [];
    render(<StrictMode><AcademicsPage /></StrictMode>);
    fireEvent.click(await screen.findByRole('button', { name: '시연 수강 신청' }));
    expect(await screen.findByText(/개인 학사·출결 화면을 비웠습니다/)).toBeInTheDocument();
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
  });

  it('keeps request form input on failure, reuses the key for the same intent and rotates on change', async () => {
    let attempt = 0;
    routes['/academics/requests'] = init => init?.method === 'POST' ? (++attempt < 3 ? new ApiError('INTERNAL', 500) : request) : [];
    render(<AcademicsPage />);
    fireEvent.click(await screen.findByRole('tab', { name: '학적 요청' }));
    const target = await screen.findByLabelText('대상 학기 ID');
    fireEvent.change(target, { target: { value: 'not-a-uuid' } });
    fireEvent.change(screen.getByLabelText('사유'), { target: { value: '가상 사유' } });
    fireEvent.click(screen.getByRole('button', { name: '임시 저장' }));
    expect(await screen.findByText(/UUID 형식/)).toBeInTheDocument();
    expect(callsTo('/academics/requests').filter(([, i]) => i?.method === 'POST')).toHaveLength(0);
    fireEvent.change(target, { target: { value: T } });
    fireEvent.click(screen.getByRole('button', { name: '임시 저장' }));
    await screen.findByText(/서버에 연결하지 못했습니다/);
    expect(screen.queryByText(/저장되었습니다/)).not.toBeInTheDocument();
    expect(screen.getByLabelText('사유')).toHaveValue('가상 사유');
    fireEvent.change(screen.getByLabelText('사유'), { target: { value: '바뀐 사유' } });
    fireEvent.click(screen.getByRole('button', { name: '임시 저장' }));
    await waitFor(() => expect(callsTo('/academics/requests').filter(([, i]) => i?.method === 'POST')).toHaveLength(2));
    fireEvent.click(screen.getByRole('button', { name: '임시 저장' }));
    expect(await screen.findByText(/시연 요청이 임시 저장 상태로 저장되었습니다/)).toBeInTheDocument();
    const posts = callsTo('/academics/requests').filter(([, i]) => i?.method === 'POST');
    expect(keyOf(posts[0][1])).not.toBe(keyOf(posts[1][1]));
    expect(keyOf(posts[1][1])).toBe(keyOf(posts[2][1]));
    expect(JSON.parse(String(posts[2][1]?.body))).toMatchObject({ kind: 'LEAVE_OF_ABSENCE', target_term_id: T, reason: '바뀐 사유' });
    expect(screen.getByText(/학교 승인·학적 반영·성적 변경 권한은 연결되지 않으며/)).toBeInTheDocument();
  });

  it('shows the demo record without a graduation judgement', async () => {
    render(<AcademicsPage />);
    fireEvent.click(await screen.findByRole('tab', { name: '성적·이수' }));
    expect(await screen.findByText(/졸업 판정: 제공하지 않음/)).toBeInTheDocument();
    expect(screen.getByText(/공식 성적·졸업 판정·증명 효력이 없으며/)).toBeInTheDocument();
  });

  it('lets a student check in with the demo code only', async () => {
    routes[`/academics/attendance/offerings/${O}/me`] = () => ({ sessions: [session], records: [], corrections: [], record_source: 'DEMO' });
    routes[`/academics/attendance/offerings/${O}/sessions/${S}/check-in`] = () => ({ id: E, session_id: S, member_ref: null, student_label: null, mark: 'CHECKED_IN', checked_in_at: AT, updated_at: AT, revision: 1, is_mine: true, judgement: 'DEMO_DISPLAY_ONLY' });
    render(<AcademicsPage />);
    fireEvent.click(await screen.findByRole('tab', { name: '출결' }));
    expect(await screen.findByText(/블루투스·캠퍼스락 신원 확인은 차단/)).toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: /가상 자료구조 · 수강생/ }));
    fireEvent.change(await screen.findByLabelText('시연 체크인 코드'), { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: '체크인' }));
    await waitFor(() => expect(callsTo(`/academics/attendance/offerings/${O}/sessions/${S}/check-in`)).toHaveLength(1));
    const [, init] = callsTo(`/academics/attendance/offerings/${O}/sessions/${S}/check-in`)[0];
    expect(JSON.parse(String(init?.body))).toEqual({ method: 'DEMO_CODE', code: '123456' });
  });

  it('shows the session code only in the teacher view', async () => {
    routes['/academics/attendance/offerings'] = () => [{ offering_id: O, title: '가상 자료구조', role: 'teacher', record_source: 'DEMO' }];
    routes[`/academics/attendance/offerings/${O}/sessions`] = () => [{ ...session, check_in_code: '654321' }];
    routes[`/academics/attendance/offerings/${O}/corrections`] = () => [];
    render(<AcademicsPage />);
    fireEvent.click(await screen.findByRole('tab', { name: '출결' }));
    fireEvent.click(await screen.findByRole('button', { name: /가상 자료구조 · 담당 교수/ }));
    expect(await screen.findByLabelText('시연 체크인 코드')).toHaveTextContent('654321');
  });
});
