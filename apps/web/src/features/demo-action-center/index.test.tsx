import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, requestData } from '../../lib/api';
import DemoActionCenter from './index';
import { isReadResult, isSummary, type DemoNotification } from './api';

vi.mock('../../lib/api', async original => ({ ...await original<typeof import('../../lib/api')>(), requestData: vi.fn() }));
const A = '11111111-1111-4111-8111-111111111111';
const B = '22222222-2222-4222-8222-222222222222';
const C = '33333333-3333-4333-8333-333333333333';
const SUMMARY_PATH = '/me/demo-action-center/summary';
const cards = () => [
  { id: 'demo-class-1', kind: 'CLASS', title: '[DEMO] 가상 자료구조 수업', detail: '가상 수업', link: '/app/classrooms', record_source: 'DEMO' },
  { id: 'demo-task-1', kind: 'TASK', title: '[DEMO] 가상 과제 제출 연습', detail: '가상 과제', link: '/app/classrooms', record_source: 'DEMO' },
  { id: 'demo-notice-1', kind: 'NOTICE', title: '<b>[DEMO] 가상 학과 안내</b>', detail: '가상 안내', link: '/app/department', record_source: 'DEMO' },
];
const note = (id: string, title: string, read = false, revision = 1): DemoNotification => ({
  id, card_id: 'demo-class-1', title, link: '/app/classrooms', read, revision, delivery: 'IN_APP_ONLY', record_source: 'DEMO',
});
const summary = (notifications = [note(A, '알림 하나'), note(B, '알림 둘'), note(C, '알림 셋')]) => ({
  mode: 'DEMO', storage: 'PROCESS_MEMORY', rule_based: true, ai_generated: false, school_connection: 'NOT_CONNECTED',
  cards: cards(), notifications, unread_count: notifications.filter(n => !n.read).length,
});
const mocked = vi.mocked(requestData);
// Server-side state for readback: POST marks A read at revision 2.
let readA = false;
const serverSummary = () => summary([note(A, '알림 하나', readA, readA ? 2 : 1), note(B, '알림 둘'), note(C, '알림 셋')]);

beforeEach(() => {
  mocked.mockReset();
  readA = false;
  mocked.mockImplementation(async (path, init) => {
    if (path === SUMMARY_PATH) return serverSummary();
    if (init?.method === 'POST') { readA = true; return { notification: note(A, '알림 하나', true, 2), already_read: false, unread_count: 2 }; }
    throw new ApiError('NOT_FOUND', 404);
  });
});

describe('가상 시연 액션 센터', () => {
  it('DEMO 카드·고정 내부 링크·미읽음 배지를 텍스트로만 표시한다', async () => {
    const view = render(<StrictMode><DemoActionCenter sessionGeneration={1} /></StrictMode>);
    expect(screen.getByRole('status')).toHaveTextContent('불러오는 중');
    expect(await screen.findByText('<b>[DEMO] 가상 학과 안내</b>')).toBeInTheDocument();
    expect(view.container.querySelector('b')).toBeNull();
    expect(screen.getByRole('link', { name: '[DEMO] 가상 자료구조 수업' })).toHaveAttribute('href', '/app/classrooms');
    expect(screen.getByLabelText('읽지 않은 가상 알림 3건')).toHaveTextContent('3');
    expect(screen.getByText(/AI가 생성하지 않았습니다/)).toBeInTheDocument();
    expect(screen.getByText(/푸시·이메일 발송이나 공식 열람 통계가 아닙니다/)).toBeInTheDocument();
    expect(mocked).toHaveBeenCalledWith(SUMMARY_PATH, expect.any(Object));
  });

  it('변조된 링크·출처·플래그·추가 필드를 거부한다', async () => {
    expect(isSummary(summary())).toBe(true);
    const external = summary(); external.cards[0].link = 'https://example.invalid/phish';
    expect(isSummary(external)).toBe(false);
    expect(isSummary({ ...summary(), ai_generated: true })).toBe(false);
    expect(isSummary({ ...summary(), storage: 'MARIADB' })).toBe(false);
    expect(isSummary({ ...summary(), owner_id: A })).toBe(false);
    expect(isSummary({ ...summary(), unread_count: 1 })).toBe(false);
    expect(isReadResult({ notification: note(A, 'x', false, 1), already_read: false, unread_count: 3 })).toBe(false);
    mocked.mockImplementation(async () => external);
    render(<DemoActionCenter sessionGeneration={1} />);
    expect(await screen.findByRole('button', { name: '가상 시연 다시 시도' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '[DEMO] 가상 자료구조 수업' })).toBeNull();
  });

  it('기본 503은 가짜 자료 없이 오류와 다시 시도를 제공한다', async () => {
    mocked.mockRejectedValue(new ApiError('UNAVAILABLE', 503));
    render(<DemoActionCenter sessionGeneration={1} />);
    fireEvent.click(await screen.findByRole('button', { name: '가상 시연 다시 시도' }));
    expect(screen.queryByText('알림 하나')).toBeNull();
    mocked.mockImplementation(async () => summary());
    fireEvent.click(await screen.findByRole('button', { name: '가상 시연 다시 시도' }));
    expect(await screen.findByText('알림 하나')).toBeInTheDocument();
  });

  it('읽음은 서버 revision으로 요청하고 성공 응답 후에만 표시한다', async () => {
    let finish!: (value: unknown) => void;
    mocked.mockImplementation(async (path, init) => {
      if (path === SUMMARY_PATH) return serverSummary();
      if (init?.method === 'POST') return new Promise(resolve => { finish = value => { readA = true; resolve(value); }; });
      throw new ApiError('NOT_FOUND', 404);
    });
    render(<DemoActionCenter sessionGeneration={1} />);
    fireEvent.click(await screen.findByRole('button', { name: '알림 하나 읽음 처리' }));
    await waitFor(() => expect(finish).toBeTypeOf('function'));
    const post = mocked.mock.calls.find(([, init]) => init?.method === 'POST')!;
    expect(post[0]).toBe(`/me/demo-action-center/notifications/${A}/read`);
    expect(JSON.parse(post[1]!.body as string)).toEqual({ revision: 1 });
    expect(screen.getByRole('button', { name: '알림 둘 읽음 처리' })).toBeDisabled();
    expect(screen.getByLabelText('읽지 않은 가상 알림 3건')).toBeInTheDocument();
    await act(async () => { finish({ notification: note(A, '알림 하나', true, 2), already_read: false, unread_count: 2 }); });
    expect(screen.queryByRole('button', { name: '알림 하나 읽음 처리' })).toBeNull();
    expect(screen.getByText('· 읽음', { exact: false })).toBeInTheDocument();
    expect(screen.getByLabelText('읽지 않은 가상 알림 2건')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '알림 둘 읽음 처리' })).not.toBeDisabled();
  });

  it('이미 읽음 응답은 서버 집계만 반영해 중복 차감하지 않는다', async () => {
    mocked.mockImplementation(async (path, init) => {
      if (path === SUMMARY_PATH) return serverSummary();
      if (init?.method === 'POST') { readA = true; return { notification: note(A, '알림 하나', true, 2), already_read: true, unread_count: 2 }; }
      throw new ApiError('NOT_FOUND', 404);
    });
    render(<DemoActionCenter sessionGeneration={1} />);
    fireEvent.click(await screen.findByRole('button', { name: '알림 하나 읽음 처리' }));
    expect(await screen.findByLabelText('읽지 않은 가상 알림 2건')).toBeInTheDocument();
  });

  it('충돌이면 성공으로 표시하지 않고 다시 불러온다', async () => {
    const original = mocked.getMockImplementation()!;
    mocked.mockImplementation(async (path, init) => { if (init?.method === 'POST') throw new ApiError('CONFLICT', 409); return original(path, init); });
    render(<DemoActionCenter sessionGeneration={1} />);
    fireEvent.click(await screen.findByRole('button', { name: '알림 하나 읽음 처리' }));
    expect(await screen.findByText(/읽음 처리 결과를 확인하지 못했습니다/)).toBeInTheDocument();
    await waitFor(() => expect(mocked.mock.calls.filter(([p]) => p === SUMMARY_PATH).length).toBe(2));
    expect(await screen.findByRole('button', { name: '알림 하나 읽음 처리' })).toBeInTheDocument();
  });

  it('401이면 개인 내용을 비우고 같은 세대에서는 다시 읽거나 쓰지 않는다', async () => {
    const view = render(<DemoActionCenter sessionGeneration={1} />);
    await screen.findByText('알림 하나');
    const original = mocked.getMockImplementation()!;
    mocked.mockImplementation(async (path, init) => { if (init?.method === 'POST') throw new ApiError('UNAUTHORIZED', 401); return original(path, init); });
    fireEvent.click(screen.getByRole('button', { name: '알림 하나 읽음 처리' }));
    expect(await screen.findByText(/개인 내용을 지웠습니다/)).toBeInTheDocument();
    expect(screen.queryByText('알림 하나')).toBeNull();
    expect(screen.queryByText('[DEMO] 가상 자료구조 수업')).toBeNull();
    expect(screen.queryByRole('button')).toBeNull();
    const calls = mocked.mock.calls.length;
    await act(async () => { await Promise.resolve(); });
    expect(mocked.mock.calls.length).toBe(calls);
    mocked.mockImplementation(original);
    view.rerender(<DemoActionCenter sessionGeneration={2} />);
    expect(await screen.findByText('알림 하나')).toBeInTheDocument();
  });

  it('요약 조회의 403도 같은 세대를 잠근다', async () => {
    mocked.mockRejectedValue(new ApiError('FORBIDDEN', 403));
    render(<DemoActionCenter sessionGeneration={1} />);
    expect(await screen.findByText(/개인 내용을 지웠습니다/)).toBeInTheDocument();
    expect(screen.queryByRole('button')).toBeNull();
    expect(mocked).toHaveBeenCalledTimes(1);
  });

  it('같은 틱의 두 번 읽음 클릭은 POST를 한 번만 보낸다', async () => {
    render(<DemoActionCenter sessionGeneration={1} />);
    const first = await screen.findByRole('button', { name: '알림 하나 읽음 처리' });
    const second = screen.getByRole('button', { name: '알림 둘 읽음 처리' });
    act(() => { first.click(); first.click(); second.click(); });
    expect(await screen.findByLabelText('읽지 않은 가상 알림 2건')).toBeInTheDocument();
    expect(mocked.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
  });

  it('POST 성공 뒤 다시 조회에 같은 읽음 영수증이 없으면 완료로 표시하지 않는다', async () => {
    mocked.mockImplementation(async (path, init) => {
      if (path === SUMMARY_PATH) return summary();
      if (init?.method === 'POST') return { notification: note(A, '알림 하나', true, 2), already_read: false, unread_count: 2 };
      throw new ApiError('NOT_FOUND', 404);
    });
    render(<DemoActionCenter sessionGeneration={1} />);
    fireEvent.click(await screen.findByRole('button', { name: '알림 하나 읽음 처리' }));
    expect(await screen.findByText(/최신 목록에서 확인하지 못했습니다/)).toBeInTheDocument();
    expect(screen.getByLabelText('읽지 않은 가상 알림 3건')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '알림 하나 읽음 처리' })).toBeInTheDocument();
  });
  it('신규 읽음 영수증의 개정이 증가하지 않으면 거짓 완료를 표시하지 않는다', async () => {
    mocked.mockImplementation(async (path, init) => {
      if (path === SUMMARY_PATH) return summary();
      if (init?.method === 'POST') return { notification: note(A, '알림 하나', true, 1), already_read: false, unread_count: 2 };
      throw new ApiError('NOT_FOUND', 404);
    });
    render(<DemoActionCenter sessionGeneration={1} />);
    fireEvent.click(await screen.findByRole('button', { name: '알림 하나 읽음 처리' }));
    expect(await screen.findByText(/읽음 처리에 실패했습니다/)).toBeInTheDocument();
    expect(mocked.mock.calls.filter(([path]) => path === SUMMARY_PATH)).toHaveLength(1);
  });

  it('세션 세대가 바뀌면 이전 내용을 지우고 진행 중 요청을 중단한다', async () => {
    const signals: AbortSignal[] = [];
    let second!: (value: unknown) => void;
    mocked.mockImplementation(async (path, init) => {
      if (init?.signal) signals.push(init.signal);
      if (path === SUMMARY_PATH && signals.length > 1) return new Promise(resolve => { second = resolve; });
      if (path === SUMMARY_PATH) return summary();
      return new Promise(() => undefined);
    });
    const view = render(<DemoActionCenter sessionGeneration={1} />);
    fireEvent.click(await screen.findByRole('button', { name: '알림 하나 읽음 처리' }));
    await waitFor(() => expect(signals).toHaveLength(2));
    view.rerender(<DemoActionCenter sessionGeneration={2} />);
    expect(signals[1].aborted).toBe(true);
    expect(screen.queryByText('알림 하나')).toBeNull();
    expect(screen.getByRole('status')).toBeInTheDocument();
    await waitFor(() => expect(second).toBeTypeOf('function'));
    await act(async () => { second(summary([note(B, '새 세션 알림')])); });
    expect(screen.getByText('새 세션 알림')).toBeInTheDocument();
    view.unmount();
    expect(signals.every(s => s.aborted)).toBe(true);
  });
});
