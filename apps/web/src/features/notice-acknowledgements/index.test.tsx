import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, requestData } from '../../lib/api';
import NoticeAcknowledgementsPage from './index';
import { isAckSummary, isOwnState } from './api';

vi.mock('../../lib/api', async original => ({ ...await original<typeof import('../../lib/api')>(), requestData: vi.fn() }));
const N = '33333333-3333-4333-8333-333333333333';
const AT = '2026-10-30T00:00:00Z';
const demo = { record_source: 'DEMO', storage: 'PROCESS_MEMORY', official_effect: false, restart_reset: true } as const;
const base = { ...demo, notice_id: N, requested: true, request_revision: 1, can_request: false, can_acknowledge: true, acknowledged: false, acknowledged_at: null, can_view_summary: false };
const mocked = vi.mocked(requestData);
const posts = () => mocked.mock.calls.filter(([, init]) => init?.method === 'POST');

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>(r => { resolve = r; });
  return { promise, resolve };
}
async function lookup() {
  fireEvent.click(screen.getByRole('button', { name: '상태 조회' }));
}

let state: Record<string, unknown>;
beforeEach(() => {
  state = { ...base };
  mocked.mockReset();
  mocked.mockImplementation(async (path, init) => {
    if (path === `/notice-acknowledgements/${N}` && !init?.method) return state;
    if (path === `/notice-acknowledgements/${N}/ack`) {
      state = { ...state, acknowledged: true, acknowledged_at: AT, can_acknowledge: false };
      return { ...demo, notice_id: N, request_revision: 1, acknowledged: true, acknowledged_at: AT };
    }
    throw new ApiError('NOT_FOUND', 404);
  });
});

describe('FR-NOT-004 공지 확인 요청 (dormant DEMO)', () => {
  it('기본 503에서 가짜 상태를 만들지 않는다', async () => {
    mocked.mockRejectedValue(new ApiError('UNAVAILABLE', 503));
    render(<NoticeAcknowledgementsPage sessionGeneration={1} initialNoticeId={N} />);
    await lookup();
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByText(/확인 요청이/)).toBeNull();
    expect(posts()).toHaveLength(0);
  });

  it('동의 전에는 기록하지 않고, 접두사를 한 번만 쓰며, 새 조회가 영수증과 일치할 때만 성공을 표시한다', async () => {
    const view = render(<NoticeAcknowledgementsPage sessionGeneration={1} initialNoticeId={N.toUpperCase()} />);
    await lookup();
    const ack = await screen.findByRole('button', { name: '확인 기록' });
    expect(ack).toBeDisabled();
    fireEvent.click(ack);
    expect(posts()).toHaveLength(0);
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(ack);
    fireEvent.click(ack);
    expect(await screen.findByRole('status')).toHaveTextContent('다시 조회로 확인');
    expect(posts()).toHaveLength(1);
    const [path, init] = posts()[0];
    expect(path).toBe(`/notice-acknowledgements/${N}/ack`);
    expect(JSON.parse(String(init?.body))).toEqual({ request_revision: 1 });
    expect((init?.headers as Record<string, string>)['Idempotency-Key']).toMatch(/^[A-Za-z0-9_-]{16,128}$/);
    for (const [p] of mocked.mock.calls) expect(p.match(/notice-acknowledgements/g)).toHaveLength(1);
    expect(view.container.textContent).not.toContain(N);
  });

  it('모호한 실패 뒤 요청 개정이 바뀌면 같은 키를 다른 본문에 재사용하지 않는다', async () => {
    const original = mocked.getMockImplementation()!;
    let failNext = true;
    mocked.mockImplementation(async (path, init) => {
      if (init?.method === 'POST' && failNext) { failNext = false; throw new ApiError('UNAVAILABLE', 503); }
      if (init?.method === 'POST') {
        const revision = JSON.parse(String(init.body)).request_revision;
        state = { ...state, acknowledged: true, acknowledged_at: AT, can_acknowledge: false };
        return { ...demo, notice_id: N, request_revision: revision, acknowledged: true, acknowledged_at: AT };
      }
      return original(path, init);
    });
    render(<NoticeAcknowledgementsPage sessionGeneration={1} initialNoticeId={N} />);
    await lookup();
    fireEvent.click(await screen.findByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '확인 기록' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('같은 요청');
    state = { ...base, request_revision: 2 };
    await lookup();
    await waitFor(() => expect(mocked.mock.calls.filter(([, init]) => !init?.method)).toHaveLength(2));
    const box = await screen.findByRole('checkbox');
    if (!(box as HTMLInputElement).checked) fireEvent.click(box);
    fireEvent.click(screen.getByRole('button', { name: '확인 기록' }));
    await waitFor(() => expect(posts()).toHaveLength(2));
    const bodies = posts().map(([, init]) => JSON.parse(String(init?.body)).request_revision);
    const keys = posts().map(([, init]) => (init?.headers as Record<string, string>)['Idempotency-Key']);
    expect(bodies).toEqual([1, 2]);
    expect(keys[1]).not.toBe(keys[0]);
  });

  it('새 조회가 영수증과 다르면 성공을 표시하지 않는다', async () => {
    const original = mocked.getMockImplementation()!;
    mocked.mockImplementation(async (path, init) => {
      const value = await original(path, init);
      if (init?.method === 'POST') state = { ...base };
      return value;
    });
    render(<NoticeAcknowledgementsPage sessionGeneration={1} initialNoticeId={N} />);
    await lookup();
    fireEvent.click(await screen.findByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '확인 기록' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('일치하지 않습니다');
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('불확실한 실패 후 자동 재시도 없이 같은 키로 수동 재시도한다', async () => {
    const original = mocked.getMockImplementation()!;
    let fail = true;
    mocked.mockImplementation(async (path, init) => {
      if (init?.method === 'POST' && fail) { fail = false; throw new ApiError('UNAVAILABLE', 503); }
      return original(path, init);
    });
    render(<NoticeAcknowledgementsPage sessionGeneration={1} initialNoticeId={N} />);
    await lookup();
    fireEvent.click(await screen.findByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '확인 기록' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('같은 요청');
    expect(posts()).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: '확인 기록' }));
    await screen.findByRole('status');
    const keys = posts().map(([, init]) => (init?.headers as Record<string, string>)['Idempotency-Key']);
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  it('소유자는 명시 동의 후 요청을 만들고 개인 식별 없는 집계만 본다', async () => {
    state = { ...base, requested: false, request_revision: null, can_request: true, can_acknowledge: false };
    mocked.mockImplementation(async (path, init) => {
      if (path === '/notice-acknowledgements/request') {
        expect(JSON.parse(String(init?.body))).toEqual({ notice_id: N, opt_in: true });
        state = { ...base, can_acknowledge: false, can_view_summary: true };
        return { ...demo, notice_id: N, request_revision: 1 };
      }
      if (path.endsWith('/summary')) return { ...demo, notice_id: N, request_revision: 1, eligible_total: 3, acknowledged_count: 2, audience_basis: 'TRUSTED_PORT_CURRENT' };
      return state;
    });
    const view = render(<NoticeAcknowledgementsPage sessionGeneration={1} initialNoticeId={N} />);
    await lookup();
    const create = await screen.findByRole('button', { name: '확인 요청 만들기' });
    expect(create).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(create);
    expect(await screen.findByText('현재 대상 3명 중 2명 확인 (개인 식별 정보 없음)')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('확인 요청이 등록');
    expect(view.container.textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
  });

  it('401/403이면 모든 개인 상태와 동의를 지우고 새 세대 전까지 비활성화한다', async () => {
    const view = render(<NoticeAcknowledgementsPage sessionGeneration={1} initialNoticeId={N} />);
    await lookup();
    fireEvent.click(await screen.findByRole('checkbox'));
    mocked.mockRejectedValue(new ApiError('FORBIDDEN', 403));
    fireEvent.click(screen.getByRole('button', { name: '확인 기록' }));
    expect(await screen.findByText(/개인 정보를 지웠습니다/)).toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).toBeNull();
    expect(screen.queryByText(/확인 요청이/)).toBeNull();
    expect(screen.getByRole('button', { name: '상태 조회' })).toBeDisabled();
    const calls = mocked.mock.calls.length;
    await lookup();
    expect(mocked.mock.calls.length).toBe(calls);
    view.rerender(<NoticeAcknowledgementsPage sessionGeneration={2} initialNoticeId={N} />);
    expect(screen.getByRole('button', { name: '상태 조회' })).toBeEnabled();
    expect(screen.queryByText(/개인 정보를 지웠습니다/)).toBeNull();
  });

  it('입력 변경·세대 교체 후 늦게 온 응답은 반영하지 않는다', async () => {
    const late = deferred<unknown>();
    mocked.mockImplementation(() => late.promise as Promise<never>);
    const view = render(<NoticeAcknowledgementsPage sessionGeneration={1} initialNoticeId={N} />);
    await lookup();
    fireEvent.change(screen.getByLabelText('공지 참조'), { target: { value: '' } });
    view.rerender(<NoticeAcknowledgementsPage sessionGeneration={2} initialNoticeId={N} />);
    late.resolve(state);
    await waitFor(() => expect(mocked).toHaveBeenCalledTimes(1));
    await Promise.resolve();
    expect(screen.queryByText(/확인 요청이/)).toBeNull();
    expect(screen.queryByRole('checkbox')).toBeNull();
    expect(screen.getByRole('button', { name: '상태 조회' })).toBeEnabled();
  });

  it('형식이 다른 응답과 잘못된 참조는 거부한다', async () => {
    expect(isOwnState({ ...state, owner_id: N }, N)).toBe(false);
    expect(isOwnState({ ...state, official_effect: true }, N)).toBe(false);
    expect(isOwnState(state, '44444444-4444-4444-8444-444444444444')).toBe(false);
    expect(isAckSummary({ ...demo, notice_id: N, request_revision: 1, eligible_total: 1, acknowledged_count: 2, audience_basis: 'TRUSTED_PORT_CURRENT' }, N)).toBe(false);
    mocked.mockResolvedValue({ ...state, students: [] });
    render(<NoticeAcknowledgementsPage sessionGeneration={1} initialNoticeId={N} />);
    await lookup();
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).toBeNull();
    fireEvent.change(screen.getByLabelText('공지 참조'), { target: { value: 'not-a-uuid' } });
    const calls = mocked.mock.calls.length;
    await lookup();
    expect(await screen.findByText('공지 참조 형식을 확인해 주세요.')).toBeInTheDocument();
    expect(mocked.mock.calls.length).toBe(calls);
  });
});
