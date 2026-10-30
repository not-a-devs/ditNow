// jsdom/RTL only with requestData mocked — not a browser, mounted-App or server verification.
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { StrictMode } from 'react';

const requestData = vi.hoisted(() => vi.fn());
vi.mock('../../lib/api', async original => {
  const actual = await original<typeof import('../../lib/api')>();
  return { ...actual, requestData };
});

import { ApiError } from '../../lib/api';
import DemoAttendance from './index';
import { parseCard, parseState, parseCheckIn } from './api';

const CARD = {
  card: {
    mode: 'DEMO', storage: 'PROCESS_MEMORY', display_alias: 'DEMO 가상 학생', card_label: 'DEMO 모바일 학생증 (시뮬레이션)',
    valid_credential: false, qr_enabled: false, notice: '시연용 가상 카드입니다.',
  },
  session: {
    session_label: 'DEMO 가상 출석 세션', method: 'NUMERIC_CODE_SIMULATION', simulation_code: '123456', notice: '가상 출석 연습입니다.',
  },
};
const EMPTY = { mode: 'DEMO', storage: 'PROCESS_MEMORY', method: 'NUMERIC_CODE_SIMULATION', checked_in: false, checked_in_at: null };
const AT = '2026-10-30T03:00:00Z';
const RESULT = (replayed: boolean) => ({ mode: 'DEMO', storage: 'PROCESS_MEMORY', method: 'NUMERIC_CODE_SIMULATION', checked_in_at: AT, replayed });

function routeReads() {
  requestData.mockImplementation(async (path: string) => {
    if (path === '/me/demo-attendance/card') return CARD;
    if (path === '/me/demo-attendance/state') return EMPTY;
    throw new Error(`unexpected ${path}`);
  });
}

afterEach(() => {
  requestData.mockReset();
});

async function ready() {
  await screen.findByText('DEMO 모바일 학생증 (시뮬레이션)');
}

function submitCode(value: string) {
  fireEvent.change(screen.getByLabelText('6자리 시연 코드'), { target: { value } });
  fireEvent.click(screen.getByRole('button', { name: '시연 출석' }));
}

describe('DemoAttendance', () => {
  it('shows the synthetic card, visible simulation code and DEMO notice', async () => {
    routeReads();
    render(<DemoAttendance sessionGeneration={1} />);
    await ready();
    expect(screen.getByText('123456')).toBeTruthy();
    expect(screen.getByText(/PROCESS_MEMORY/)).toBeTruthy();
    expect(screen.getByText('신분 증명 효력 없음 · QR 미제공')).toBeTruthy();
    expect(screen.getByText('아직 시연 출석 전입니다.')).toBeTruthy();
  });

  it('posts only the code and reports first check-in then replay', async () => {
    routeReads();
    render(<DemoAttendance sessionGeneration={1} />);
    await ready();
    requestData.mockResolvedValueOnce(RESULT(false));
    submitCode('123456');
    expect(await screen.findByText('시연 출석이 기록되었습니다.')).toBeTruthy();
    const [path, init] = requestData.mock.calls.at(-1)!;
    expect(path).toBe('/me/demo-attendance/check-in');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ code: '123456' });

    requestData.mockResolvedValueOnce(RESULT(true));
    submitCode('123456');
    expect(await screen.findByText('이미 시연 출석이 기록되어 있습니다.')).toBeTruthy();
    expect(screen.getByText(/시연 출석 완료/)).toBeTruthy();
  });

  it('blocks malformed codes client-side and shows 422 mismatch', async () => {
    routeReads();
    render(<DemoAttendance sessionGeneration={1} />);
    await ready();
    const calls = requestData.mock.calls.length;
    submitCode('12');
    expect(await screen.findByText('6자리 숫자 코드를 입력하세요.')).toBeTruthy();
    expect(requestData.mock.calls.length).toBe(calls);

    requestData.mockRejectedValueOnce(new ApiError('VALIDATION', 422));
    submitCode('654321');
    expect(await screen.findByText('시연 코드가 일치하지 않습니다.')).toBeTruthy();
  });

  it('resets code, result and notice when the session generation changes', async () => {
    routeReads();
    const { rerender } = render(<DemoAttendance sessionGeneration={1} />);
    await ready();
    requestData.mockResolvedValueOnce(RESULT(false));
    submitCode('123456');
    await screen.findByText('시연 출석이 기록되었습니다.');
    fireEvent.change(screen.getByLabelText('6자리 시연 코드'), { target: { value: '9' } });

    routeReads();
    rerender(<DemoAttendance sessionGeneration={2} />);
    await ready();
    expect(screen.queryByText('시연 출석이 기록되었습니다.')).toBeNull();
    expect((screen.getByLabelText('6자리 시연 코드') as HTMLInputElement).value).toBe('');
    expect(screen.getByText('아직 시연 출석 전입니다.')).toBeTruthy();
  });

  it('ignores a late check-in reply after the generation changes', async () => {
    routeReads();
    const { rerender } = render(<DemoAttendance sessionGeneration={1} />);
    await ready();
    let resolve!: (value: unknown) => void;
    let signal: AbortSignal | undefined;
    requestData.mockImplementationOnce((_path: string, init: RequestInit) => {
      signal = init.signal ?? undefined;
      return new Promise(r => { resolve = r; });
    });
    submitCode('123456');
    routeReads();
    rerender(<DemoAttendance sessionGeneration={2} />);
    await ready();
    expect(signal?.aborted).toBe(true);
    await act(async () => { resolve(RESULT(false)); });
    expect(screen.queryByText('시연 출석이 기록되었습니다.')).toBeNull();
    expect(screen.getByText('아직 시연 출석 전입니다.')).toBeTruthy();
  });

  it('aborts pending reads on unmount', async () => {
    const signals: AbortSignal[] = [];
    requestData.mockImplementation((_path: string, init: RequestInit) => {
      if (init.signal) signals.push(init.signal);
      return new Promise(() => {});
    });
    const { unmount } = render(<DemoAttendance sessionGeneration={1} />);
    await waitFor(() => expect(signals.length).toBe(2));
    unmount();
    expect(signals.every(s => s.aborted)).toBe(true);
  });

  it('shows a load error instead of a card', async () => {
    requestData.mockRejectedValue(new ApiError('UNAVAILABLE', 503));
    render(<DemoAttendance sessionGeneration={1} />);
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.queryByText('123456')).toBeNull();
  });

  it.each([401, 403])('discards card, input and private state immediately on %i', async status => {
    routeReads();
    render(<DemoAttendance sessionGeneration={1} />);
    await ready();
    requestData.mockRejectedValueOnce(new ApiError(status === 401 ? 'UNAUTHORIZED' : 'FORBIDDEN', status));
    submitCode('123456');
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByText('DEMO 모바일 학생증 (시뮬레이션)')).toBeNull();
    expect(screen.queryByLabelText('6자리 시연 코드')).toBeNull();
    expect(screen.queryByText('123456')).toBeNull();
  });
  it('StrictMode aborts discarded reads and same-tick submissions write only once', async () => {
    routeReads();
    render(<StrictMode><DemoAttendance sessionGeneration={1} /></StrictMode>);
    await ready();
    expect(requestData.mock.calls[0][1]?.signal?.aborted).toBe(true);
    let finish!: (value: unknown) => void;
    requestData.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    fireEvent.change(screen.getByLabelText('6자리 시연 코드'), { target: { value: '123456' } });
    const form = screen.getByRole('button', { name: '시연 출석' }).closest('form')!;
    const before = requestData.mock.calls.length;
    act(() => { fireEvent.submit(form); fireEvent.submit(form); });
    expect(requestData.mock.calls.length).toBe(before + 1);
    await act(async () => finish(RESULT(false)));
    expect(screen.getByText('시연 출석이 기록되었습니다.')).toBeInTheDocument();
  });
});

describe('demo attendance guards', () => {
  it('rejects cards that claim a valid credential or QR', () => {
    expect(() => parseCard({ ...CARD, card: { ...CARD.card, valid_credential: true } })).toThrow();
    expect(() => parseCard({ ...CARD, card: { ...CARD.card, qr_enabled: true } })).toThrow();
    expect(() => parseCard({ ...CARD, card: { ...CARD.card, mode: 'LIVE' } })).toThrow();
  });

  it('rejects inconsistent state', () => {
    expect(() => parseState({ ...EMPTY, checked_in: true })).toThrow();
    expect(() => parseState({ ...EMPTY, storage: 'MARIADB' })).toThrow();
  });
  it('rejects an invented method and malformed attendance timestamps', () => {
    expect(() => parseState({ ...EMPTY, method: 'BLUETOOTH' })).toThrow();
    expect(() => parseCheckIn({ ...RESULT(false), method: 'REAL_ATTENDANCE' })).toThrow();
    for (const time of ['not-a-date', '2026-10-30T03:00:00', '2026-02-30T03:00:00Z']) {
      expect(() => parseState({ ...EMPTY, checked_in: true, checked_in_at: time })).toThrow();
      expect(() => parseCheckIn({ ...RESULT(false), checked_in_at: time })).toThrow();
    }
  });
});
