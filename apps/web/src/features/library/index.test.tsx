import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, requestData, resolveApiUrl } from '../../lib/api';
import LibraryPage from './index';
import { isCatalog, isOverview } from './models';

vi.mock('../../lib/api', async importOriginal => ({ ...await importOriginal<typeof import('../../lib/api')>(), requestData: vi.fn() }));
afterEach(() => vi.mocked(requestData).mockReset());
const loanId = '11111111-1111-4111-8111-111111111111';
const bookId = '22222222-2222-4222-8222-222222222222';
const slotId = '33333333-3333-4333-8333-333333333333';
const source_kind = 'DEMO';
const catalog = { items: [{ id: bookId, title: '가상 개발 도서', author: '가상 저자', available_copies: 1, public_reference_url: null, source_kind }], offset: 0, has_more: false, source_kind };
const loan = { id: loanId, title: '나의 가상 대출', due_at: '2026-11-01T00:00:00Z', state: 'active', renewal_count: 0, renewable: true, revision: 1, source_kind };
const slot = { id: slotId, space_id: bookId, space_name: '가상 그룹실', starts_at: '2026-11-01T00:00:00Z', ends_at: '2026-11-01T01:00:00Z', available: true, revision: 1, source_kind };
const overview = { loans: [loan], wishes: [], bookings: [], policy: { name: '가상 테스트 규칙', renewal_days: 7, max_renewals: 1, allow_overdue_renewal: false, renewal_base: 'due_at', max_active_bookings: 1, source_kind }, source_kind };

function mocks(onMutation?: (path: string, init?: RequestInit) => Promise<unknown>) {
  vi.mocked(requestData).mockImplementation(async (path, init) => {
    if (init?.method === 'POST') { if (onMutation) return onMutation(path, init); throw new ApiError('UNAVAILABLE', 503); }
    if (path.startsWith('/library/catalog')) return catalog;
    if (path === '/library/slots') return [slot];
    if (path === '/library/me') return overview;
    throw new Error('unexpected path');
  });
}
async function ready() { render(<LibraryPage />); await screen.findByText('나의 가상 대출'); }

describe('library first-pass UI', () => {
  it('reports unavailable providers without inventing loan or booking records', async () => {
    vi.mocked(requestData).mockRejectedValue(new ApiError('UNAVAILABLE', 503));
    render(<LibraryPage />);
    expect(await screen.findAllByRole('alert')).toHaveLength(3);
    expect(screen.queryByLabelText('도서명')).not.toBeInTheDocument();
    expect(screen.getByText(/실제 학교 도서관·전자정보·시설 예약과 연결되지/)).toBeInTheDocument();
  });
  it('uses the single API prefix and labels supplied policy as demonstration only', async () => {
    mocks(); await ready();
    expect(screen.getByText(/주입된 가상 정책/)).toHaveTextContent('학교 공식 규정이 아닙니다');
    expect(requestData).toHaveBeenCalledWith('/library/me', expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(resolveApiUrl('/library/me', '')).toBe(`${window.location.origin}/api/v1/library/me`);
    expect(screen.getByRole('button', { name: '시연 예약' })).toBeEnabled();
  });
  it('keeps wish text and idempotency key across uncertain retries', async () => {
    let failures = 0;
    mocks(async (_path, init) => {
      if (failures++ === 0) throw new ApiError('NETWORK', 0);
      return { ...JSON.parse(String(init?.body)), id: bookId, state: 'requested', created_at: '2026-10-30T00:00:00Z', source_kind };
    });
    await ready();
    fireEvent.change(screen.getByLabelText('도서명'), { target: { value: '가상 희망 책' } });
    fireEvent.change(screen.getByLabelText('저자'), { target: { value: '가상 저자' } });
    fireEvent.change(screen.getByLabelText(/요청 사유/), { target: { value: '남겨둘 시연 사유' } });
    fireEvent.click(screen.getByRole('button', { name: '시연 요청 저장' }));
    await screen.findByRole('alert');
    expect(screen.getByLabelText('도서명')).toHaveValue('가상 희망 책');
    expect(screen.getByLabelText(/요청 사유/)).toHaveValue('남겨둘 시연 사유');
    fireEvent.click(screen.getByRole('button', { name: '시연 요청 저장' }));
    expect(await screen.findByText('가상 희망 책')).toBeInTheDocument();
    const calls = vi.mocked(requestData).mock.calls.filter(([, init]) => init?.method === 'POST');
    expect((calls[0][1]?.headers as Record<string, string>)['Idempotency-Key']).toBe((calls[1][1]?.headers as Record<string, string>)['Idempotency-Key']);
    expect(screen.getByLabelText('도서명')).toHaveValue('');
  });
  it('keeps a booking conflict visible without displaying false success', async () => {
    mocks(async () => { throw new ApiError('CONFLICT', 409); }); await ready();
    fireEvent.click(screen.getByRole('button', { name: '시연 예약' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('내용이 변경되었습니다');
    expect(screen.getByText('본인 가상 예약이 없습니다.')).toBeInTheDocument();
    expect(screen.queryByText(/가상 공간 예약을 저장했습니다/)).not.toBeInTheDocument();
  });
  it('rotates the retry key after the user changes the failed payload', async () => {
    let attempts = 0;
    mocks(async (_path, init) => {
      if (attempts++ === 0) throw new ApiError('NETWORK', 0);
      return { ...JSON.parse(String(init?.body)), id: bookId, state: 'requested', created_at: '2026-10-30T00:00:00Z', source_kind };
    });
    await ready();
    fireEvent.change(screen.getByLabelText('도서명'), { target: { value: '첫 가상 도서' } });
    fireEvent.change(screen.getByLabelText('저자'), { target: { value: '가상 저자' } });
    fireEvent.click(screen.getByRole('button', { name: '시연 요청 저장' })); await screen.findByRole('alert');
    fireEvent.change(screen.getByLabelText('도서명'), { target: { value: '바꾼 가상 도서' } });
    fireEvent.click(screen.getByRole('button', { name: '시연 요청 저장' })); await screen.findByText('바꾼 가상 도서');
    const calls = vi.mocked(requestData).mock.calls.filter(([, init]) => init?.method === 'POST');
    expect((calls[0][1]?.headers as Record<string, string>)['Idempotency-Key']).not.toBe((calls[1][1]?.headers as Record<string, string>)['Idempotency-Key']);
  });
  it('reuses a cancellation key after a network failure and displays cancellation only on confirmation', async () => {
    let cancellations = 0;
    const booking = { id: bookId, slot_id: slotId, space_name: '가상 그룹실', starts_at: slot.starts_at, ends_at: slot.ends_at, state: 'reserved', revision: 1, source_kind };
    mocks(async path => {
      if (path.endsWith('/reserve')) return booking;
      if (cancellations++ === 0) throw new ApiError('NETWORK', 0);
      return { ...booking, state: 'cancelled', revision: 2 };
    });
    await ready(); fireEvent.click(screen.getByRole('button', { name: '시연 예약' }));
    fireEvent.click(await screen.findByRole('button', { name: '시연 예약 취소' })); await screen.findByRole('alert');
    expect(screen.getByText(/가상 예약됨/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '시연 예약 취소' })); await screen.findByText(/가상 취소됨/);
    const calls = vi.mocked(requestData).mock.calls.filter(([path]) => path.endsWith('/cancel'));
    expect((calls[0][1]?.headers as Record<string, string>)['Idempotency-Key']).toBe((calls[1][1]?.headers as Record<string, string>)['Idempotency-Key']);
  });
  it.each([401, 403])('clears personal records and preserves permission error: %i', async status => {
    mocks(async () => { throw new ApiError(status === 401 ? 'UNAUTHORIZED' : 'FORBIDDEN', status); }); await ready();
    fireEvent.click(screen.getByRole('button', { name: '시연 연장' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(status === 401 ? '로그인이 필요한' : '접근할 권한');
    expect(screen.queryByText('나의 가상 대출')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('도서명')).not.toBeInTheDocument();
    expect(screen.getByText('가상 개발 도서')).toBeInTheDocument();
  });
  it('rejects unsafe links and owner identities at the response boundary', () => {
    expect(isCatalog({ ...catalog, items: [{ ...catalog.items[0], public_reference_url: 'javascript:alert(1)' }] })).toBe(false);
    expect(isCatalog({ ...catalog, items: [{ ...catalog.items[0], public_reference_url: 'https://user:secret@example.test' }] })).toBe(false);
    expect(isOverview({ ...overview, loans: [{ ...loan, owner_id: 'private-user' }] })).toBe(false);
  });
  it('cancels all in-flight reads on unmount', async () => {
    vi.mocked(requestData).mockImplementation(() => new Promise(() => {}));
    const view = render(<LibraryPage />);
    await waitFor(() => expect(requestData).toHaveBeenCalledTimes(3));
    const signals = vi.mocked(requestData).mock.calls.map(([, init]) => init?.signal);
    view.unmount(); expect(signals.every(signal => signal?.aborted)).toBe(true);
  });
});
