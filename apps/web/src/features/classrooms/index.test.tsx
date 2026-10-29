import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ApiError, requestData } from '../../lib/api';
import ClassroomsPage from './index';
import { isWorkspace } from './models';

vi.mock('../../lib/api', async importOriginal => ({ ...await importOriginal<typeof import('../../lib/api')>(), requestData: vi.fn() }));
const offering = { id: '11111111-1111-4111-8111-111111111111', title: '가상 소프트웨어 수업', term: '가상 학기', section: 'A', instructor_name: '가상 교수', source_kind: 'DEMO' };
const assignment = { id: '22222222-2222-4222-8222-222222222222', title: '가상 과제', instructions: '시연 텍스트', deadline_at: '2026-11-01T00:00:00Z', status: 'published', revision: 1 };
const workspace = { offering, role: 'student', materials: [], assignments: [assignment], questions: [], submissions: [], source_kind: 'DEMO' };

async function openWorkspace() {
  vi.mocked(requestData).mockResolvedValueOnce([offering]).mockResolvedValueOnce(workspace);
  render(<ClassroomsPage />);
  fireEvent.click(await screen.findByRole('button', { name: /가상 소프트웨어 수업/ }));
  await screen.findByRole('heading', { name: '가상 소프트웨어 수업' });
}

describe('classroom first-pass screen', () => {
  it('fails closed without an approved provider and offers retry', async () => {
    vi.mocked(requestData).mockRejectedValueOnce(new ApiError('UNAVAILABLE', 503));
    render(<ClassroomsPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('공통 인증·수강·저장소 연결');
    expect(screen.getByRole('button', { name: '목록 다시 확인' })).toBeEnabled();
    expect(screen.queryByLabelText('교수에게 질문')).not.toBeInTheDocument();
  });
  it('shows an honest empty offering list', async () => {
    vi.mocked(requestData).mockResolvedValueOnce([]);
    render(<ClassroomsPage />);
    expect(await screen.findByText(/현재 승인된 강의실이 없습니다/)).toBeInTheDocument();
    expect(requestData).toHaveBeenCalledWith('/classrooms', expect.objectContaining({ signal: expect.any(AbortSignal) }));
  });
  it('loads only selected offering and shows demo limits', async () => {
    await openWorkspace();
    expect(requestData).toHaveBeenLastCalledWith(`/classrooms/${offering.id}`, expect.any(Object));
    expect(screen.getByText(/실제 학교 학적·성적·온라인 출석/)).toBeInTheDocument();
    expect(screen.getByText(/본인과 담당 교수에게만/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '질문 보내기' })).toBeDisabled();
  });
  it('sends a private question with an idempotency key and no claimed actor', async () => {
    await openWorkspace();
    const question = { id: '33333333-3333-4333-8333-333333333333', text: '질문 내용', answer: null, state: 'open', visibility: 'teacher_only', created_at: '2026-10-30T00:00:00Z', revision: 1, is_mine: true };
    vi.mocked(requestData).mockResolvedValueOnce(question);
    fireEvent.change(screen.getByLabelText('교수에게 질문'), { target: { value: '질문 내용' } });
    fireEvent.click(screen.getByRole('button', { name: '질문 보내기' }));
    expect(await screen.findByText('질문 내용')).toBeInTheDocument();
    const [, init] = vi.mocked(requestData).mock.calls.at(-1)!;
    expect(init?.body).toBe(JSON.stringify({ text: '질문 내용' }));
    expect((init?.headers as Record<string, string>)['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/);
    expect(screen.queryByRole('button', { name: '답변 등록' })).not.toBeInTheDocument();
  });
  it('keeps submission text on stale-version rejection', async () => {
    await openWorkspace();
    vi.mocked(requestData).mockRejectedValueOnce(new ApiError('CONFLICT', 409));
    fireEvent.change(screen.getByLabelText('시연 텍스트 과제'), { target: { value: '내 시연 제출' } });
    fireEvent.click(screen.getByRole('button', { name: '시연 과제 제출' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('내용이 변경되었습니다');
    expect(screen.getByLabelText('시연 텍스트 과제')).toHaveValue('내 시연 제출');
    expect(vi.mocked(requestData).mock.calls.at(-1)?.[1]?.body).toBe(JSON.stringify({ text: '내 시연 제출', expected_revision: 0 }));
  });
  it('rejects author IDs and unsafe material URLs before rendering', () => {
    expect(isWorkspace({ ...workspace, questions: [{ author_id: 'private' }] })).toBe(false);
    expect(isWorkspace({ ...workspace, materials: [{ id: assignment.id, title: '자료', description: '', status: 'published', public_reference_url: 'javascript:alert(1)' }] })).toBe(false);
  });
  it.each([401, 403])('clears private workspace and keeps the permission failure visible: %i', async status => {
    await openWorkspace();
    vi.mocked(requestData).mockRejectedValueOnce(new ApiError(status === 401 ? 'UNAUTHORIZED' : 'FORBIDDEN', status));
    fireEvent.change(screen.getByLabelText('시연 텍스트 과제'), { target: { value: '내 시연 제출' } });
    fireEvent.click(screen.getByRole('button', { name: '시연 과제 제출' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(status === 401 ? '로그인이 필요한' : '접근할 권한');
    expect(screen.queryByLabelText('시연 텍스트 과제')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('교수에게 질문')).not.toBeInTheDocument();
  });
  it('cancels pending reads on unmount', async () => {
    let signal: AbortSignal | undefined;
    vi.mocked(requestData).mockImplementationOnce((_path, init) => { signal = init?.signal as AbortSignal; return new Promise(() => {}); });
    const view = render(<ClassroomsPage />);
    await waitFor(() => expect(signal).toBeDefined());
    view.unmount(); expect(signal?.aborted).toBe(true);
  });
});
