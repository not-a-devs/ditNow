import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import CampusTravelPage from './index';
import { calculateTravel, kstInput, NOTICE, type TravelInput } from './api';

const input: TravelInput = { previous_ends_at: '2026-10-30T10:00:00+09:00', next_starts_at: '2026-10-30T10:15:00+09:00', estimated_travel_minutes: 10 };
function result(body = input) {
  const gap = (Date.parse(body.next_starts_at) - Date.parse(body.previous_ends_at)) / 1000;
  const travel = body.estimated_travel_minutes * 60, left = gap - travel;
  return { previous_ends_at: new Date(body.previous_ends_at).toISOString().replace('.000Z', 'Z'), next_starts_at: new Date(body.next_starts_at).toISOString().replace('.000Z', 'Z'), gap_seconds: gap, travel_seconds: travel, remaining_seconds: left, status: gap < 0 ? 'OVERLAP' : left < 0 ? 'INSUFFICIENT' : left === 0 ? 'NO_MARGIN' : 'HAS_MARGIN', estimate_source: 'USER_INPUT', calculation_version: 'manual-travel-v1', notice: NOTICE };
}
const response = (data: unknown = result()) => new Response(JSON.stringify({ data }), { status: 200 });
function fill() {
  fireEvent.change(screen.getByLabelText('앞 수업 종료 시각 (KST)'), { target: { value: '2026-10-30T10:00' } });
  fireEvent.change(screen.getByLabelText('다음 수업 시작 시각 (KST)'), { target: { value: '2026-10-30T10:15' } });
  fireEvent.change(screen.getByLabelText('내가 예상한 이동 시간 (분)'), { target: { value: '10' } });
}
beforeEach(() => { vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response())); });
afterEach(() => { vi.unstubAllGlobals(); });

describe('manual travel contract', () => {
  it('uses KST explicitly, one API prefix, POST body and no shared cache', async () => {
    expect(kstInput('2026-10-30T10:00', '2026-10-30T10:15', '10')).toEqual(input);
    expect((await calculateTravel(input)).remaining_seconds).toBe(300);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toBe(`${location.origin}/api/v1/campus-travel/calculate`);
    expect(init?.method).toBe('POST'); expect(init?.cache).toBe('no-store');
    expect(JSON.parse(String(init?.body))).toEqual(input);
    expect(String(url)).not.toContain('2026');
  });
  it.each(['2026-02-30T10:00', '2026-10-30T24:00', '1999-10-30T10:00'])('rejects invalid calendar time %s', value => {
    expect(() => kstInput(value, '2026-10-30T10:15', '10')).toThrow();
    expect(fetch).not.toHaveBeenCalled();
  });
  it('handles next-day UTC/KST and zero-gap calculation without inventing a safety buffer', async () => {
    const midnight = kstInput('2026-10-30T23:55', '2026-10-31T00:10', '15');
    vi.mocked(fetch).mockResolvedValueOnce(response(result(midnight)));
    expect((await calculateTravel(midnight)).status).toBe('NO_MARGIN');
    const same = { ...input, next_starts_at: input.previous_ends_at, estimated_travel_minutes: 0 };
    vi.mocked(fetch).mockResolvedValueOnce(response(result(same)));
    expect((await calculateTravel(same)).remaining_seconds).toBe(0);
  });
  it('accepts a valid offset input whose normalized UTC date is in the previous year', async () => {
    const edge = kstInput('2000-01-01T00:00', '2000-01-01T00:15', '10');
    vi.mocked(fetch).mockResolvedValueOnce(response(result(edge)));
    expect((await calculateTravel(edge)).previous_ends_at).toBe('1999-12-31T15:00:00Z');
  });
  it('rejects an empty server result', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(response(null));
    await expect(calculateTravel(input)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  });
  it.each([-1, 1441, 1.5, NaN])('rejects technical minute bound %s before transport', async minutes => {
    await expect(calculateTravel({ ...input, estimated_travel_minutes: minutes })).rejects.toMatchObject({ code: 'VALIDATION' });
    expect(fetch).not.toHaveBeenCalled();
  });
  it.each([{ estimate_source: 'OFFICIAL' }, { remaining_seconds: 999 }, { status: 'INSUFFICIENT' }, { user_id: 'private' }])('rejects mismatched or unexpected result %j', async changes => {
    vi.mocked(fetch).mockResolvedValue(response({ ...result(), ...changes }));
    await expect(calculateTravel(input)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  });
});

describe('manual travel screen', () => {
  it('has an empty form and displays limitations, loading and actual server result', async () => {
    let resolve!: (v: Response) => void;
    vi.mocked(fetch).mockReturnValue(new Promise(r => { resolve = r; }));
    render(<CampusTravelPage />);
    expect(screen.getByText('두 시각과 예상 이동 시간을 입력해 주세요.')).toBeInTheDocument();
    expect(screen.getByText(NOTICE)).toBeInTheDocument();
    fill(); fireEvent.click(screen.getByRole('button', { name: '입력 기준으로 계산' }));
    expect(screen.getByRole('button', { name: '계산 중…' })).toBeDisabled();
    await act(async () => resolve(response()));
    expect(await screen.findByText('남는 시간: 5분')).toBeInTheDocument();
    expect(screen.getByText(/예상 시간 출처: 사용자 입력/)).toBeInTheDocument();
  });
  it.each([401, 503])('shows safe HTTP %s error and can retry the stateless intent', async status => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ code: status === 401 ? 'UNAUTHORIZED' : 'UNAVAILABLE' }), { status }));
    render(<CampusTravelPage />); fill(); fireEvent.click(screen.getByRole('button', { name: '입력 기준으로 계산' }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '입력 기준으로 계산' }));
    expect(await screen.findByText('남는 시간: 5분')).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it('discards a late result after editing and accepts only the latest input', async () => {
    let old!: (v: Response) => void;
    vi.mocked(fetch).mockReturnValueOnce(new Promise(r => { old = r; }));
    render(<CampusTravelPage />); fill(); fireEvent.click(screen.getByRole('button', { name: '입력 기준으로 계산' }));
    fireEvent.change(screen.getByLabelText('내가 예상한 이동 시간 (분)'), { target: { value: '20' } });
    vi.mocked(fetch).mockResolvedValueOnce(response(result({ ...input, estimated_travel_minutes: 20 })));
    fireEvent.click(screen.getByRole('button', { name: '입력 기준으로 계산' }));
    expect(await screen.findByText('부족: 5분')).toBeInTheDocument();
    await act(async () => old(response()));
    expect(screen.queryByText('남는 시간: 5분')).not.toBeInTheDocument();
    expect(screen.getByText('부족: 5분')).toBeInTheDocument();
  });
  it('aborts on unmount and ignores late errors', async () => {
    let reject!: (e: Error) => void;
    vi.mocked(fetch).mockReturnValueOnce(new Promise((_, r) => { reject = r; }));
    const view = render(<CampusTravelPage />); fill(); fireEvent.click(screen.getByRole('button', { name: '입력 기준으로 계산' }));
    const signal = vi.mocked(fetch).mock.calls[0][1]?.signal;
    view.unmount(); expect(signal?.aborted).toBe(true);
    await act(async () => reject(new Error('private failure')));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  });
});
