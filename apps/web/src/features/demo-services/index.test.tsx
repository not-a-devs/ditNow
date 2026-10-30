import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../lib/api';

vi.mock('./api', async importOriginal => ({ ...(await importOriginal<typeof import('./api')>()), list: vi.fn(), create: vi.fn(), advance: vi.fn(), remove: vi.fn() }));

import * as api from './api';
import DemoStudentServices from './index';

const ID = '3f1c2b4a-5d6e-4f70-8a9b-0c1d2e3f4a5b';
const item = (patch: Partial<api.Item> = {}): api.Item => ({ id: ID, kind: 'ADMISSION_RESULT', scenario: 'STANDARD', status: 'REQUESTED', status_label: '가상 접수', revision: 1,
  created_at: '2026-10-30T01:00:00Z', updated_at: '2026-10-30T01:00:00Z', title: '가상 입학결과 예시', outcome_text: null, document_text: null,
  source_kind: 'DEMO', persistence: 'PROCESS_MEMORY', official_effect: false, sensitive_content_collected: false, ...patch });
const page = (items: api.Item[] = []): api.Page => ({ source_kind: 'DEMO', persistence: 'PROCESS_MEMORY', official_effect: false, items });
function deferred<T>() { let resolve!: (value: T) => void, reject!: (cause: unknown) => void; const promise = new Promise<T>((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; }
const m = vi.mocked(api);
const writes = () => m.create.mock.calls.length + m.advance.mock.calls.length + m.remove.mock.calls.length;
const createButton = () => screen.getByRole('button', { name: '확인하고 가상 요청 만들기' });
beforeEach(() => { vi.resetAllMocks(); m.list.mockResolvedValue(page()); });

describe('DemoStudentServices', () => {
  it('shows warning, five keyboard tabs and empty state without any writes', async () => {
    render(<DemoStudentServices sessionGeneration={1} />);
    expect(screen.getByText('가상 요청을 조회 중…')).toBeTruthy();
    expect(await screen.findByText(/조회만으로 요청이 생성되지 않습니다/)).toBeTruthy();
    expect(screen.getAllByText(/공식 효력 없음/).length).toBeGreaterThan(0);
    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(5);
    fireEvent.keyDown(tabs[0], { key: 'ArrowRight' });
    expect(screen.getAllByRole('tab')[1].getAttribute('aria-selected')).toBe('true');
    await waitFor(() => expect(m.list).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('textbox')).toBeNull();
    expect((createButton() as HTMLButtonElement).disabled).toBe(true);
    fireEvent.submit(createButton().closest('form')!);
    expect(writes()).toBe(0);
  });

  it('shows 503 as disconnected, never as success', async () => {
    m.list.mockRejectedValue(new ApiError('UNAVAILABLE', 503));
    render(<DemoStudentServices sessionGeneration={1} />);
    expect((await screen.findByRole('alert')).textContent).toContain('연결되지 않았습니다');
    expect(screen.queryByText(/다시 확인했습니다/)).toBeNull();
    expect(screen.queryByText(/조회만으로 요청이 생성되지 않습니다/)).toBeNull();
    expect((screen.getByRole('checkbox') as HTMLInputElement).disabled).toBe(true);
  });

  it('creates only after consent and reports completion only after a fresh GET', async () => {
    render(<DemoStudentServices sessionGeneration={1} />);
    await screen.findByText(/조회만으로/);
    m.create.mockResolvedValue(item({ scenario: 'REVIEW_EXAMPLE' }));
    const reread = deferred<api.Page>(); m.list.mockReturnValueOnce(reread.promise);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'REVIEW_EXAMPLE' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(createButton());
    await waitFor(() => expect(m.list).toHaveBeenCalledTimes(2));
    const [body, key] = m.create.mock.calls[0];
    expect(body).toEqual({ kind: 'ADMISSION_RESULT', scenario: 'REVIEW_EXAMPLE', consent: true });
    expect(key).toMatch(/^[A-Za-z0-9_-]{16,100}$/);
    expect(screen.queryByText(/다시 확인했습니다/)).toBeNull();
    await act(async () => reread.resolve(page([item({ scenario: 'REVIEW_EXAMPLE' })])));
    expect(await screen.findByText(/서버 목록을 다시 확인했습니다/)).toBeTruthy();
    expect(screen.getByText('가상 입학결과 예시')).toBeTruthy();
  });

  it('requires explicit second confirmation for advance and cancel, then rereads', async () => {
    m.list.mockResolvedValueOnce(page([item()])).mockResolvedValueOnce(page([item({ status: 'IN_PROGRESS', revision: 2 })])).mockResolvedValueOnce(page());
    m.advance.mockResolvedValue(item({ status: 'IN_PROGRESS', revision: 2 }));
    m.remove.mockResolvedValue(undefined);
    render(<DemoStudentServices sessionGeneration={1} />);
    fireEvent.click(await screen.findByRole('button', { name: '가상 처리 한 단계 진행' }));
    expect(m.advance).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '확인하고 가상 단계 진행' }));
    await screen.findByText(/서버 목록을 다시 확인했습니다/);
    expect(m.advance.mock.calls[0][0]).toMatchObject({ id: ID, revision: 1 });
    expect(m.list).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole('button', { name: '가상 요청 취소' }));
    expect(m.remove).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '확인하고 가상 요청 취소' }));
    await screen.findByText(/취소 후 목록을 다시 확인했습니다/);
    expect(m.list).toHaveBeenCalledTimes(3);
  });

  it('retries an ambiguous failure with the same key/body only on request and blocks double submit', async () => {
    render(<DemoStudentServices sessionGeneration={1} />);
    await screen.findByText(/조회만으로/);
    const first = deferred<api.Item>(); m.create.mockReturnValueOnce(first.promise);
    fireEvent.click(screen.getByRole('checkbox'));
    const form = createButton().closest('form')!;
    fireEvent.submit(form); fireEvent.submit(form);
    expect(m.create).toHaveBeenCalledTimes(1);
    await act(async () => first.reject(new TypeError('network')));
    const retry = await screen.findByRole('button', { name: '같은 요청 다시 확인' });
    expect(m.create).toHaveBeenCalledTimes(1);
    m.create.mockResolvedValueOnce(item());
    m.list.mockResolvedValueOnce(page([item()]));
    fireEvent.click(retry);
    await screen.findByText(/서버 목록을 다시 확인했습니다/);
    expect(m.create.mock.calls[1][0]).toEqual(m.create.mock.calls[0][0]);
    expect(m.create.mock.calls[1][1]).toBe(m.create.mock.calls[0][1]);
  });

  it('discards old account data on generation change even if the old request ignores abort', async () => {
    const old = deferred<api.Page>(); m.list.mockReturnValueOnce(old.promise).mockResolvedValueOnce(page());
    const view = render(<DemoStudentServices sessionGeneration="a" />);
    const oldSignal = m.list.mock.calls[0][0]!;
    view.rerender(<DemoStudentServices sessionGeneration="b" />);
    expect(oldSignal.aborted).toBe(true);
    await screen.findByText(/조회만으로/);
    await act(async () => old.resolve(page([item({ title: '이전 계정 가상 기록' })])));
    expect(screen.queryByText('이전 계정 가상 기록')).toBeNull();
  });

  it('does not claim creation if fresh GET is missing it and preserves the retry key', async () => {
    render(<DemoStudentServices sessionGeneration={1} />);
    await screen.findByText(/조회만으로/);
    m.create.mockResolvedValue(item());
    fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(createButton());
    const retry = await screen.findByRole('button', { name: '같은 요청 다시 확인' });
    expect(screen.queryByText(/서버 목록을 다시 확인했습니다/)).toBeNull();
    m.list.mockResolvedValueOnce(page([item()]));
    fireEvent.click(retry);
    await screen.findByText(/서버 목록을 다시 확인했습니다/);
    expect(m.create.mock.calls[1][1]).toBe(m.create.mock.calls[0][1]);
  });

  it('does not claim cancellation if fresh GET still contains the record', async () => {
    m.list.mockResolvedValue(page([item()])); m.remove.mockResolvedValue(undefined);
    render(<DemoStudentServices sessionGeneration={1} />);
    fireEvent.click(await screen.findByRole('button', { name: '가상 요청 취소' }));
    fireEvent.click(screen.getByRole('button', { name: '확인하고 가상 요청 취소' }));
    const retry = await screen.findByRole('button', { name: '같은 요청 다시 확인' });
    expect(screen.queryByText(/취소 후 목록을 다시 확인했습니다/)).toBeNull();
    m.list.mockResolvedValueOnce(page()); fireEvent.click(retry);
    await screen.findByText(/취소 후 목록을 다시 확인했습니다/);
    expect(m.remove.mock.calls[1][0]).toEqual(m.remove.mock.calls[0][0]);
  });

  it('does not reread after unmount before a mutation response', async () => {
    const view = render(<DemoStudentServices sessionGeneration={1} />);
    await screen.findByText(/조회만으로/);
    const pending = deferred<api.Item>(); m.create.mockReturnValueOnce(pending.promise);
    fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(createButton());
    view.unmount();
    await act(async () => pending.resolve(item()));
    expect(m.list).toHaveBeenCalledTimes(1);
  });

  it('never rereads or shows old mutations after switching accounts', async () => {
    const view = render(<DemoStudentServices sessionGeneration="A" />);
    await screen.findByText(/조회만으로/);
    const old = deferred<api.Item>(); m.create.mockReturnValueOnce(old.promise);
    fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(createButton());
    const signal = m.create.mock.calls[0][2]!;
    view.rerender(<DemoStudentServices sessionGeneration="B" />);
    await screen.findByText(/조회만으로/);
    expect(signal.aborted).toBe(true);
    await act(async () => old.resolve(item()));
    expect(m.list).toHaveBeenCalledTimes(2);
    expect(screen.queryByText('가상 입학결과 예시')).toBeNull();
    expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false);
    expect(screen.queryByRole('button', { name: '같은 요청 다시 확인' })).toBeNull();
  });

  it('renders the active response under StrictMode', async () => {
    m.list.mockResolvedValue(page([item()]));
    render(<StrictMode><DemoStudentServices sessionGeneration={1} /></StrictMode>);
    expect(await screen.findByText('가상 입학결과 예시')).toBeTruthy();
    expect(m.list.mock.calls[0][0]!.aborted).toBe(true);
  });

  it.each([401, 403])('%i clears records and blocks tabs until generation changes', async status => {
    m.list.mockResolvedValueOnce(page([item()])).mockRejectedValueOnce(new ApiError('DENIED', status));
    const view = render(<DemoStudentServices sessionGeneration={1} />);
    await screen.findByText('가상 입학결과 예시');
    fireEvent.click(screen.getByRole('button', { name: '가상 요청 다시 조회' }));
    await screen.findByRole('alert');
    expect(screen.queryByText('가상 입학결과 예시')).toBeNull();
    expect(screen.queryByRole('checkbox')).toBeNull();
    screen.getAllByRole('tab').forEach(tab => expect((tab as HTMLButtonElement).disabled).toBe(true));
    fireEvent.keyDown(screen.getAllByRole('tab')[0], { key: 'End' });
    fireEvent.click(screen.getAllByRole('tab')[4]);
    expect(m.list).toHaveBeenCalledTimes(2);
    view.rerender(<DemoStudentServices sessionGeneration={1} />);
    expect(m.list).toHaveBeenCalledTimes(2);
    m.list.mockResolvedValueOnce(page());
    view.rerender(<DemoStudentServices sessionGeneration={2} />);
    await screen.findByText(/조회만으로/);
    expect((screen.getAllByRole('tab')[4] as HTMLButtonElement).disabled).toBe(false);
    expect(writes()).toBe(0);
  });

  it('blocks writes after a stale 409 until a fresh GET succeeds', async () => {
    m.list.mockResolvedValue(page([item()]));
    m.advance.mockRejectedValueOnce(new ApiError('CONFLICT', 409));
    render(<DemoStudentServices sessionGeneration={1} />);
    fireEvent.click(await screen.findByRole('button', { name: '가상 처리 한 단계 진행' }));
    fireEvent.click(screen.getByRole('button', { name: '확인하고 가상 단계 진행' }));
    expect((await screen.findByRole('alert')).textContent).toContain('다시 조회');
    expect((screen.getByRole('checkbox') as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: '가상 처리 한 단계 진행' }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole('button', { name: '같은 요청 다시 확인' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '가상 요청 다시 조회' }));
    await waitFor(() => expect((screen.getByRole('checkbox') as HTMLInputElement).disabled).toBe(false));
    expect(m.advance).toHaveBeenCalledTimes(1);
  });
});
