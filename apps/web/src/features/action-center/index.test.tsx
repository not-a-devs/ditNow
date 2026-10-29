import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, requestData } from '../../lib/api';
import ActionCenterPage from './index';
import { isPage, isSummary, type Notification } from './api';

vi.mock('../../lib/api', async original => ({ ...await original<typeof import('../../lib/api')>(), requestData: vi.fn() }));
const A = '11111111-1111-4111-8111-111111111111';
const B = '22222222-2222-4222-8222-222222222222';
const C = '33333333-3333-4333-8333-333333333333';
const AT = '2026-10-30T01:00:00Z';
const summary = (unread = 1) => ({
  local_date: '2026-10-30', utc_offset: '+09:00', window_start: '2026-10-29T15:00:00Z', window_end: '2026-10-30T15:00:00Z',
  classes: [{ source_type: 'CLASS_SESSION', source_id: A, title: '가상 자료구조', at: AT, link: '/app/classrooms', record_source: 'DEMO' }],
  tasks: [], notices: [{ source_type: 'NOTICE', source_id: B, title: '<b>가상 공지</b>', at: AT, link: '/app/department', record_source: 'PLATFORM' }],
  deadlines: [{ source_type: 'OPPORTUNITY_DEADLINE', source_id: C, title: '공개 장학 마감', at: AT, link: '/app/opportunities', record_source: 'OFFICIAL_PUBLIC' }],
  unread_notifications: unread, unread_capped: false, ordering: 'TIME_ASC_DEMO', priority_policy: 'NOT_DEFINED', school_connection: 'NOT_CONNECTED',
});
const note = (id: string, title: string, read_at: string | null = null, revision = 1): Notification => ({ id, source_type: 'NOTICE', source_id: B, title, link: '/app/department', record_source: 'PLATFORM', created_at: AT, read_at, revision, delivery: 'IN_APP_ONLY' });
const page = (items: Notification[], offset = 0, next_offset: number | null = null) => ({ items, offset, limit: 20, next_offset });
const mocked = vi.mocked(requestData);

beforeEach(() => {
  mocked.mockReset();
  mocked.mockImplementation(async (path, init) => {
    if (path === '/action-center/summary') return summary();
    if (path.startsWith('/action-center/notifications?')) return page([note(A, '가상 알림')]);
    if (init?.method === 'POST') return note(A, '가상 알림', AT, 2);
    throw new ApiError('NOT_FOUND', 404);
  });
});

describe('홈 요약·개인 알림함 1차 구현', () => {
  it('기본 503은 가짜 데이터 없이 오류와 다시 시도를 제공한다', async () => {
    mocked.mockRejectedValue(new ApiError('UNAVAILABLE', 503));
    render(<ActionCenterPage />);
    expect(await screen.findByRole('button', { name: '오늘 요약 다시 시도' })).toBeInTheDocument();
    expect(screen.queryByText('가상 자료구조')).toBeNull();
    mocked.mockImplementation(async path => path === '/action-center/summary' ? summary() : page([]));
    fireEvent.click(screen.getByRole('button', { name: '오늘 요약 다시 시도' }));
    expect(await screen.findByText('가상 자료구조')).toBeInTheDocument();
  });

  it('원본 참조를 출처 표시·고정 내부 링크·텍스트로만 보여 준다', async () => {
    const view = render(<StrictMode><ActionCenterPage /></StrictMode>);
    expect(await screen.findByText('<b>가상 공지</b>')).toBeInTheDocument();
    expect(view.container.querySelector('b')).toBeNull();
    expect(screen.getByRole('link', { name: '가상 자료구조' })).toHaveAttribute('href', '/app/classrooms');
    expect(screen.getAllByText('플랫폼 공지').length).toBeGreaterThan(0);
    expect(screen.getByText('공개 자료 인용')).toBeInTheDocument();
    expect(screen.getByText('가상 시연 자료')).toBeInTheDocument();
    expect(screen.getByText('7일 안에 마감되는 과제가 없습니다.')).toBeInTheDocument();
    expect(screen.getByText(/읽지 않은 알림 1건/)).toBeInTheDocument();
    expect(mocked).toHaveBeenCalledWith('/action-center/notifications?offset=0&limit=20', expect.any(Object));
  });

  it('외부 링크·출처 불일치·추가 필드 응답을 거부한다', async () => {
    expect(isSummary(summary())).toBe(true);
    const tampered = summary(); tampered.classes[0].link = 'https://example.invalid/phish';
    expect(isSummary(tampered)).toBe(false);
    const relabeled = summary(); relabeled.notices[0].record_source = 'DEMO';
    expect(isSummary(relabeled)).toBe(false);
    expect(isPage({ ...page([note(A, '가상')]), recipient_id: A })).toBe(false);
    mocked.mockImplementation(async path => path === '/action-center/summary' ? tampered : page([]));
    render(<ActionCenterPage />);
    expect(await screen.findByRole('button', { name: '오늘 요약 다시 시도' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '가상 자료구조' })).toBeNull();
  });

  it.each([200, 201])('서버와 동일하게 보조 평면 문자의 %s 코드포인트 제목 경계를 검사한다', length => {
    const wireTitle = String.fromCodePoint(0x1f642).repeat(length);
    const payload = summary(); payload.classes[0].title = wireTitle;
    expect(Array.from(wireTitle)).toHaveLength(length);
    expect(wireTitle).toHaveLength(length * 2);
    expect(isSummary(payload)).toBe(length === 200);
    expect(isPage(page([note(A, wireTitle)]))).toBe(length === 200);
  });

  it('읽음 처리는 서버 revision으로 요청하고 성공 응답 후에만 표시한다', async () => {
    render(<ActionCenterPage />);
    fireEvent.click(await screen.findByRole('button', { name: '가상 알림 읽음 처리' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: '가상 알림 읽음 처리' })).toBeNull());
    expect(screen.getByText(/· 읽음$/)).toBeInTheDocument();
    const post = mocked.mock.calls.find(([, init]) => init?.method === 'POST')!;
    expect(post[0]).toBe(`/action-center/notifications/${A}/read`);
    expect(JSON.parse(post[1]!.body as string)).toEqual({ expected_revision: 1 });
    expect(mocked.mock.calls.filter(([p]) => p === '/action-center/summary').length).toBeGreaterThanOrEqual(2);
  });

  it('충돌이면 성공으로 표시하지 않고 알림함을 다시 읽는다', async () => {
    const original = mocked.getMockImplementation()!;
    mocked.mockImplementation(async (path, init) => { if (init?.method === 'POST') throw new ApiError('CONFLICT', 409); return original(path, init); });
    render(<ActionCenterPage />);
    fireEvent.click(await screen.findByRole('button', { name: '가상 알림 읽음 처리' }));
    expect(await screen.findByText(/읽음 처리 결과를 확인하지 못했습니다/)).toBeInTheDocument();
    await waitFor(() => expect(mocked.mock.calls.filter(([p]) => String(p).startsWith('/action-center/notifications?')).length).toBe(2));
    expect(screen.getByRole('button', { name: '가상 알림 읽음 처리' })).toBeInTheDocument();
  });

  it('늦게 도착한 이전 페이지 응답을 반영하지 않는다', async () => {
    let late: (value: unknown) => void = () => undefined;
    mocked.mockImplementation(async path => {
      if (path === '/action-center/summary') return summary();
      if (path.includes('offset=20')) return new Promise(resolve => { late = resolve; });
      return page([note(A, '첫 페이지 알림')], 0, 20);
    });
    render(<ActionCenterPage />);
    await screen.findByText('첫 페이지 알림');
    fireEvent.click(screen.getByRole('button', { name: '다음' }));
    fireEvent.click(screen.getByRole('button', { name: '이전' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '다음' })).not.toBeDisabled());
    await act(async () => { late(page([note(B, '늦은 다음 페이지')], 20)); });
    expect(screen.queryByText('늦은 다음 페이지')).toBeNull();
    expect(screen.getByText('첫 페이지 알림')).toBeInTheDocument();
  });

  it('401이면 개인 내용을 비우고 권한 재확인을 제공한다', async () => {
    render(<ActionCenterPage />);
    await screen.findByText('가상 자료구조');
    const original = mocked.getMockImplementation()!;
    mocked.mockImplementation(async (path, init) => { if (init?.method === 'POST') throw new ApiError('UNAUTHORIZED', 401); return original(path, init); });
    fireEvent.click(screen.getByRole('button', { name: '가상 알림 읽음 처리' }));
    expect(await screen.findByRole('button', { name: '권한 다시 확인' })).toBeInTheDocument();
    expect(screen.queryByText('가상 자료구조')).toBeNull();
    expect(screen.queryByText('가상 알림')).toBeNull();
  });
});
