import { StrictMode } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../lib/api';
import * as api from './api';
import AdminChangeRequestsPage from './index';

vi.mock('./api', async () => ({ ...await vi.importActual<typeof import('./api')>('./api'),
  loadProposals: vi.fn(), createProposal: vi.fn(), submitProposal: vi.fn(), withdrawProposal: vi.fn() }));
const draft: api.Proposal = {
  id: '00000000-0000-4000-8000-000000000001', target_code: 'STUDENT_DEMO_A', proposal_scope: 'DEPARTMENT_STUDENT', reason_code: 'ACADEMIC_DEMO',
  state: 'DRAFT', revision: 1, created_at: '2026-10-30T02:00:00Z', updated_at: '2026-10-30T02:00:00Z', submitted_at: null, withdrawn_at: null,
  record_source: 'DEMO', storage: 'PROCESS_MEMORY', official_effect: false, restart_reset: true, replayed: false,
};
const submitted: api.Proposal = { ...draft, state: 'SUBMITTED', revision: 2, submitted_at: '2026-10-30T02:01:00Z' };
const listOf = (...items: api.Proposal[]): api.ProposalList => ({ items, owner_cap: 20, record_source: 'DEMO', storage: 'PROCESS_MEMORY', official_effect: false, restart_reset: true });
function deferred<T>() { let resolve!: (value: T) => void, reject!: (cause: unknown) => void; const promise = new Promise<T>((ok, no) => { resolve = ok; reject = no; }); return { promise, resolve, reject }; }
const consent = () => screen.getByRole('checkbox');
const createButton = () => screen.getByRole('button', { name: '시연 초안 만들기' });

beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.loadProposals).mockResolvedValue(listOf()); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('관리 변경 제안 화면 (시연)', () => {
  it('실제 관리자 기능이 아님을 알리고 동의 없이는 쓰지 않는다', async () => {
    render(<StrictMode><AdminChangeRequestsPage /></StrictMode>);
    await screen.findByText('본인 제안이 없습니다.');
    expect(screen.getByText(/실제 관리자 기능이 아니며/)).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(createButton()).toBeDisabled();
    fireEvent.submit(createButton().closest('form')!);
    expect(api.createProposal).not.toHaveBeenCalled();
  });
  it('생성 후 새 조회가 영수증과 일치할 때만 성공을 표시한다', async () => {
    vi.mocked(api.createProposal).mockResolvedValue(draft);
    render(<AdminChangeRequestsPage />); await screen.findByText('본인 제안이 없습니다.');
    vi.mocked(api.loadProposals).mockResolvedValueOnce(listOf(draft));
    fireEvent.click(consent()); fireEvent.click(createButton());
    await screen.findByText(/새 조회로 확인했습니다/);
    expect(vi.mocked(api.createProposal).mock.calls[0][0]).toEqual({ target_code: 'STUDENT_DEMO_A', proposal_scope: 'DEPARTMENT_STUDENT', reason_code: 'ACADEMIC_DEMO', consent: true });
    expect(consent()).not.toBeChecked();
  });
  it('영수증과 새 조회가 다르면 성공을 주장하지 않는다', async () => {
    vi.mocked(api.loadProposals).mockResolvedValueOnce(listOf(draft)).mockResolvedValueOnce(listOf(draft));
    vi.mocked(api.submitProposal).mockResolvedValue(submitted);
    render(<AdminChangeRequestsPage />);
    fireEvent.click(await screen.findByRole('button', { name: '제출' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('성공으로 표시하지 않았습니다');
    expect(screen.queryByText(/제출 상태로 바꿨습니다/)).not.toBeInTheDocument();
  });
  it('모호한 오류는 자동 재시도하지 않고 같은 입력의 수동 재시도는 같은 키를 쓴다', async () => {
    vi.mocked(api.createProposal).mockRejectedValueOnce(new TypeError('network')).mockResolvedValueOnce(draft);
    render(<AdminChangeRequestsPage />); await screen.findByText('본인 제안이 없습니다.');
    fireEvent.click(consent()); fireEvent.click(createButton());
    expect(await screen.findByRole('alert')).toHaveTextContent('자동 재시도하지 않습니다');
    expect(api.createProposal).toHaveBeenCalledTimes(1);
    vi.mocked(api.loadProposals).mockResolvedValueOnce(listOf(draft));
    fireEvent.click(createButton());
    await screen.findByText(/새 조회로 확인했습니다/);
    const keys = vi.mocked(api.createProposal).mock.calls.map(call => call[1]);
    expect(keys[0]).toBe(keys[1]);
  });
  it('바쁜 동안 두 번째 클릭은 요청을 보내지 않는다', async () => {
    const pending = deferred<api.Proposal>(); vi.mocked(api.createProposal).mockReturnValue(pending.promise);
    render(<AdminChangeRequestsPage />); await screen.findByText('본인 제안이 없습니다.');
    fireEvent.click(consent());
    const form = createButton().closest('form')!;
    fireEvent.submit(form); fireEvent.submit(form);
    expect(api.createProposal).toHaveBeenCalledTimes(1);
    vi.mocked(api.loadProposals).mockResolvedValueOnce(listOf(draft));
    await act(async () => pending.resolve(draft));
  });
  it('403이면 개인 상태·동의를 지우고 새 세션 세대 전까지 비활성화한다', async () => {
    vi.mocked(api.loadProposals).mockResolvedValueOnce(listOf(draft));
    vi.mocked(api.withdrawProposal).mockRejectedValue(new ApiError('FORBIDDEN', 403));
    const view = render(<AdminChangeRequestsPage sessionGeneration={0} />);
    fireEvent.click(await screen.findByRole('button', { name: '철회' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('권한은 이 화면에서 부여되지 않습니다');
    expect(screen.queryByText(/가상 학생 A/)).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '목록 다시 조회' })).toBeDisabled();
    expect(api.loadProposals).toHaveBeenCalledTimes(1);
    vi.mocked(api.loadProposals).mockResolvedValueOnce(listOf());
    view.rerender(<AdminChangeRequestsPage sessionGeneration={1} />);
    await screen.findByText('본인 제안이 없습니다.');
    expect(screen.getByRole('button', { name: '목록 다시 조회' })).toBeEnabled();
  });
  it('401 조회도 개인 상태를 지운다', async () => {
    vi.mocked(api.loadProposals).mockRejectedValueOnce(new ApiError('UNAUTHORIZED', 401));
    render(<AdminChangeRequestsPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('로그인이 만료');
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });
  it('이전 세대의 늦은 조회 응답은 새 세대 화면에 나타나지 않는다', async () => {
    const late = deferred<api.ProposalList>();
    vi.mocked(api.loadProposals).mockReturnValueOnce(late.promise).mockResolvedValueOnce(listOf());
    const view = render(<AdminChangeRequestsPage sessionGeneration={0} />);
    view.rerender(<AdminChangeRequestsPage sessionGeneration={1} />);
    await screen.findByText('본인 제안이 없습니다.');
    await act(async () => late.resolve(listOf(draft)));
    // 고정 선택지(option)에도 같은 문구가 있으므로 실제 목록 행(listitem)으로 판정한다.
    expect(screen.queryAllByRole('listitem')).toHaveLength(0);
    expect(screen.queryByRole('button', { name: '제출' })).not.toBeInTheDocument();
    expect(screen.getByText('본인 제안이 없습니다.')).toBeInTheDocument();
  });
  it('세대 변경 후 도착한 쓰기 영수증은 확인 조회도 성공 표시도 하지 않는다', async () => {
    vi.mocked(api.loadProposals).mockResolvedValueOnce(listOf(draft)).mockResolvedValue(listOf());
    const late = deferred<api.Proposal>(); vi.mocked(api.submitProposal).mockReturnValue(late.promise);
    const view = render(<AdminChangeRequestsPage sessionGeneration={0} />);
    fireEvent.click(await screen.findByRole('button', { name: '제출' }));
    view.rerender(<AdminChangeRequestsPage sessionGeneration={1} />);
    await screen.findByText('본인 제안이 없습니다.');
    const callsBefore = vi.mocked(api.loadProposals).mock.calls.length;
    await act(async () => late.resolve(submitted));
    expect(vi.mocked(api.loadProposals).mock.calls.length).toBe(callsBefore);
    expect(screen.queryByText(/제출 상태로 바꿨습니다/)).not.toBeInTheDocument();
  });
  it('503은 기본 비활성으로 안내하고 쓰기 화면을 열지 않는다', async () => {
    vi.mocked(api.loadProposals).mockRejectedValueOnce(new ApiError('UNAVAILABLE', 503));
    render(<AdminChangeRequestsPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('기본 비활성');
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: '목록 다시 조회' })).toBeEnabled());
  });
  it('저장소를 쓰지 않는다', async () => {
    const set = vi.spyOn(Storage.prototype, 'setItem');
    render(<AdminChangeRequestsPage />); await screen.findByText('본인 제안이 없습니다.');
    expect(set).not.toHaveBeenCalled();
  });
});
