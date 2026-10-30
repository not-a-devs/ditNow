import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, requestData } from '../../lib/api';
import AdminAuditQueuePage from './index';
import type { Item } from './api';

vi.mock('../../lib/api', async original => ({ ...await original<typeof import('../../lib/api')>(), requestData: vi.fn() }));
const mocked = vi.mocked(requestData);
const A = '11111111-1111-4111-8111-111111111111';
const meta = { source_kind: 'DEMO', storage: 'PROCESS_MEMORY', official_effect: false, restart_reset: true } as const;
const pending = (): Item => ({ id: A, category: 'REPORT', demo_label: 'DEMO_ITEM_01', status: 'PENDING', classification: null, resolution: null, note_code: null, revision: 1, meta });
const classified = (): Item => ({ ...pending(), status: 'CLASSIFIED', classification: 'NO_ACTION', note_code: 'DEMO_CHECKED', revision: 2 });
const page = (items: Item[]) => ({ items, meta });
const patches = () => mocked.mock.calls.filter(([, init]) => init?.method === 'PATCH');
function deferred<T>() { let resolve!: (v: T) => void; let reject!: (e: unknown) => void; const promise = new Promise<T>((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; }

let server: Item;
beforeEach(() => {
  server = pending();
  mocked.mockReset();
  mocked.mockImplementation(async (path, init) => {
    if (init?.method === 'PATCH') { server = classified(); return server; }
    if (path.startsWith('/admin-audit-queue?') || path === '/admin-audit-queue') return page([server]);
    if (path === `/admin-audit-queue/${A}`) return server;
    throw new ApiError('NOT_FOUND', 404);
  });
});

async function openAndFill() {
  render(<AdminAuditQueuePage />);
  fireEvent.click(await screen.findByRole('button', { name: 'DEMO_ITEM_01 열기' }));
  await screen.findByRole('region', { name: '선택한 항목' });
  fireEvent.change(screen.getByLabelText('분류 선택'), { target: { value: 'NO_ACTION' } });
  fireEvent.change(screen.getByLabelText('메모 코드'), { target: { value: 'DEMO_CHECKED' } });
}
const save = () => screen.getByRole('button', { name: /시연 처리 저장|저장 중/ });
const confirm = () => fireEvent.click(screen.getByRole('checkbox'));

describe('운영 감사 큐 시연 UI', () => {
  it('기본 503은 시연 데이터 없이 오류와 다시 시도를 보여 준다', async () => {
    mocked.mockRejectedValue(new ApiError('UNAVAILABLE', 503));
    render(<AdminAuditQueuePage />);
    expect(await screen.findByRole('button', { name: '목록 다시 시도' })).toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent('PROCESS_MEMORY');
    expect(screen.queryByText(/DEMO_ITEM_01/)).toBeNull();
    expect(patches()).toHaveLength(0);
  });

  it('명시적 확인 없이 저장하지 않고 자유 입력란이 없다', async () => {
    await openAndFill();
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(save()).toBeDisabled();
    fireEvent.submit(save().closest('form')!);
    expect(patches()).toHaveLength(0);
  });

  it('저장 후 재조회가 영수증과 일치할 때만 성공을 표시한다', async () => {
    await openAndFill();
    confirm();
    fireEvent.click(save());
    expect(await screen.findByText(/서버 재조회로 확인되었습니다\(revision 2\)/)).toBeInTheDocument();
    const [, init] = patches()[0];
    expect(JSON.parse(init!.body as string)).toEqual({ revision: 1, classification: 'NO_ACTION', note_code: 'DEMO_CHECKED' });
    const idx = mocked.mock.calls.findIndex(([, i]) => i?.method === 'PATCH');
    expect(mocked.mock.calls[idx + 1][0]).toBe(`/admin-audit-queue/${A}`);
    expect(screen.getByRole('checkbox')).not.toBeChecked();
  });

  it('재조회가 영수증과 다르면 성공을 표시하지 않는다', async () => {
    await openAndFill();
    mocked.mockImplementation(async (path, init) => {
      if (init?.method === 'PATCH') return classified();
      if (path === `/admin-audit-queue/${A}`) return { ...classified(), classification: 'REVIEW_NEEDED' };
      return page([pending()]);
    });
    confirm();
    fireEvent.click(save());
    expect(await screen.findByText(/일치하지 않습니다/)).toBeInTheDocument();
    expect(screen.queryByText(/서버 재조회로 확인되었습니다/)).toBeNull();
  });

  it('동기 busy ref로 연속 클릭 시 PATCH를 한 번만 보낸다', async () => {
    await openAndFill();
    const gate = deferred<Item>();
    mocked.mockImplementation(async (path, init) => init?.method === 'PATCH' ? gate.promise : path === `/admin-audit-queue/${A}` ? classified() : page([classified()]));
    confirm();
    const form = save().closest('form')!;
    fireEvent.submit(form); fireEvent.submit(form); fireEvent.submit(form);
    expect(patches()).toHaveLength(1);
    await act(async () => gate.resolve(classified()));
    await screen.findByText(/서버 재조회로 확인되었습니다/);
  });

  it('모호한 실패는 자동 재전송하지 않고 같은 의도 재시도에 같은 키를 쓴다', async () => {
    await openAndFill();
    mocked.mockImplementation(async (path, init) => {
      if (init?.method === 'PATCH') throw new ApiError('NETWORK', 0);
      return path === `/admin-audit-queue/${A}` ? pending() : page([pending()]);
    });
    confirm();
    fireEvent.click(save());
    expect(await screen.findByText(/자동으로 다시 보내지 않았습니다/)).toBeInTheDocument();
    expect(patches()).toHaveLength(1);
    expect(save()).toBeDisabled();
    confirm();
    fireEvent.click(save());
    await waitFor(() => expect(patches()).toHaveLength(2));
    const keys = patches().map(([, init]) => (init!.headers as Record<string, string>)['Idempotency-Key']);
    expect(keys[0]).toBe(keys[1]);
    expect(keys[0].length).toBeGreaterThanOrEqual(16);
  });

  it('403은 모든 비공개 상태와 확인을 지우고 새 세대 전까지 비활성화한다', async () => {
    await openAndFill();
    confirm();
    mocked.mockImplementation(async (_path, init) => { if (init?.method === 'PATCH') throw new ApiError('FORBIDDEN', 403); return page([pending()]); });
    fireEvent.click(save());
    expect(await screen.findByText(/화면의 내용을 모두 비웠습니다/)).toBeInTheDocument();
    expect(screen.queryByText(/DEMO_ITEM_01/)).toBeNull();
    expect(screen.queryByRole('checkbox')).toBeNull();
    // No local reset control: only a parent-verified session generation change re-enables.
    expect(screen.queryByRole('button', { name: '권한 다시 확인' })).toBeNull();
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    const before = mocked.mock.calls.length;
    await act(async () => {});
    expect(mocked.mock.calls.length).toBe(before);
  });

  it('거부 후 같은 세대 재렌더는 추가 요청 없이 비활성, 세대가 바뀌어야 다시 조회한다', async () => {
    mocked.mockRejectedValueOnce(new ApiError('UNAUTHORIZED', 401));
    const view = render(<AdminAuditQueuePage sessionGeneration={3} />);
    expect(await screen.findByText(/화면의 내용을 모두 비웠습니다/)).toBeInTheDocument();
    const before = mocked.mock.calls.length;
    view.rerender(<AdminAuditQueuePage sessionGeneration={3} />);
    await act(async () => {});
    expect(mocked.mock.calls.length).toBe(before);
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    mocked.mockImplementation(async () => page([pending()]));
    view.rerender(<AdminAuditQueuePage sessionGeneration={4} />);
    expect(await screen.findByRole('button', { name: 'DEMO_ITEM_01 열기' })).toBeInTheDocument();
    expect(mocked.mock.calls.length).toBe(before + 1);
    expect(screen.queryByRole('checkbox')).toBeNull();
  });

  it('세션 세대가 바뀌면 이전 세대의 늦은 목록 응답을 버린다', async () => {
    const late = deferred<unknown>();
    mocked.mockImplementationOnce(() => late.promise as Promise<never>);
    const view = render(<AdminAuditQueuePage sessionGeneration={1} />);
    mocked.mockImplementation(async () => page([]));
    view.rerender(<AdminAuditQueuePage sessionGeneration={2} />);
    expect(await screen.findByText('조건에 맞는 시연 항목이 없습니다.')).toBeInTheDocument();
    await act(async () => late.resolve(page([pending()])));
    expect(screen.queryByText(/DEMO_ITEM_01/)).toBeNull();
  });

  it('세대 전환 뒤 도착한 PATCH 영수증은 재조회·성공 표시를 하지 않는다', async () => {
    const gate = deferred<Item>();
    const view = render(<AdminAuditQueuePage sessionGeneration={1} />);
    fireEvent.click(await screen.findByRole('button', { name: 'DEMO_ITEM_01 열기' }));
    await screen.findByRole('region', { name: '선택한 항목' });
    fireEvent.change(screen.getByLabelText('분류 선택'), { target: { value: 'NO_ACTION' } });
    fireEvent.change(screen.getByLabelText('메모 코드'), { target: { value: 'DEMO_CHECKED' } });
    confirm();
    mocked.mockImplementation(async (path, init) => init?.method === 'PATCH' ? gate.promise : path === `/admin-audit-queue/${A}` ? classified() : page([]));
    fireEvent.click(save());
    expect(patches()).toHaveLength(1);
    view.rerender(<AdminAuditQueuePage sessionGeneration={2} />);
    const callsBefore = mocked.mock.calls.length;
    await act(async () => gate.resolve(classified()));
    expect(mocked.mock.calls.slice(callsBefore).some(([p]) => p === `/admin-audit-queue/${A}`)).toBe(false);
    expect(screen.queryByText(/서버 재조회로 확인되었습니다/)).toBeNull();
  });

  it('409 충돌 시 성공을 표시하지 않고 최신 상태를 다시 읽는다', async () => {
    await openAndFill();
    mocked.mockImplementation(async (path, init) => {
      if (init?.method === 'PATCH') throw new ApiError('CONFLICT', 409);
      return path === `/admin-audit-queue/${A}` ? classified() : page([classified()]);
    });
    confirm();
    fireEvent.click(save());
    expect(await screen.findByLabelText('처리 선택')).toBeInTheDocument();
    expect(screen.queryByText(/서버 재조회로 확인되었습니다/)).toBeNull();
  });
});
