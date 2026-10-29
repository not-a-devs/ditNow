import { StrictMode } from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, requestData } from '../../lib/api';
import NoticeDiscussionPage from './index';
import { isItem, isNotice, isPage, type Item } from './api';

vi.mock('../../lib/api', async original => ({ ...await original<typeof import('../../lib/api')>(), requestData: vi.fn() }));
const D = '11111111-1111-4111-8111-111111111111';
const ID = '22222222-2222-4222-8222-222222222222';
const N = '33333333-3333-4333-8333-333333333333';
const AT = '2026-10-30T00:00:00Z';
const row: Item = { id: ID, department_id: D, kind: 'QUESTION', question_id: null, title: '가상 질문', body: '가상 본문', revision: 1, created_at: AT, updated_at: AT, is_mine: true, record_source: 'DEMO', identity_display_policy: 'BLOCKED' };
const notice = { id: N, title: '가상 공지', body: '<script>unsafe-private</script>', status: 'PUBLISHED', revision: 2, updated_at: AT, school_connection: 'NOT_CONNECTED', attachments: [{ id: ID, filename: '안내.pdf', size_bytes: 23, storage: 'NOT_CONNECTED' }], history: [{ revision: 1, changed_at: AT, event: 'CREATED' }] };
let items: Item[];
beforeEach(() => {
  items = [];
  vi.mocked(requestData).mockReset();
  vi.mocked(requestData).mockImplementation(async (path, init) => {
    if (path.startsWith('/notice-discussion/notices?')) return [{ id: N, title: '가상 공지', status: 'PUBLISHED', revision: 2 }];
    if (path === '/notice-discussion/notices/' + N) return notice;
    if (path.includes('/questions?')) return { items, offset: 0, limit: 10 };
    if (init?.method === 'POST') { items = [row]; return row; }
    throw new ApiError('NOT_FOUND', 404);
  });
});

describe('공지·학과 질문 부분 구현', () => {
  it('기본 503을 가짜 데이터나 로그인으로 대체하지 않는다', async () => {
    vi.mocked(requestData).mockRejectedValue(new ApiError('UNAVAILABLE', 503));
    render(<NoticeDiscussionPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('공통 인증');
    expect(screen.queryByText('가상 공지')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '학과 질문' }));
    expect(screen.getByText(/승인된 공통 원장에서 현재 학과/)).toBeInTheDocument();
  });

  it('원본 상세를 자체 표시하고 첨부 다운로드나 과거 본문을 만들지 않는다', async () => {
    const view = render(<NoticeDiscussionPage />);
    fireEvent.click(await screen.findByRole('button', { name: '내용과 이력 보기' }));
    expect(await screen.findByText('<script>unsafe-private</script>')).toBeInTheDocument();
    expect(view.container.querySelector('script')).toBeNull();
    expect(screen.getByText('안내.pdf · 23 bytes')).toBeInTheDocument();
    expect(screen.getByText('파일 저장·다운로드 미연결')).toBeInTheDocument();
    expect(screen.queryByRole('link')).toBeNull();
    expect(vi.mocked(requestData)).toHaveBeenCalledWith('/notice-discussion/notices/' + N, expect.any(Object));
  });

  it('현재 학과가 있을 때만 질문 요청을 보내고 불확실한 실패 후 같은 키와 입력을 유지한다', async () => {
    const original = vi.mocked(requestData).getMockImplementation()!;
    let attempts = 0;
    vi.mocked(requestData).mockImplementation(async (path, init) => {
      if (init?.method === 'POST' && ++attempts === 1) throw new ApiError('NETWORK', 0);
      return original(path, init);
    });
    render(<StrictMode><NoticeDiscussionPage departmentId={D} /></StrictMode>);
    fireEvent.click(screen.getByRole('button', { name: '학과 질문' }));
    const form = screen.getByRole('form', { name: '시연 질문 작성·수정' });
    fireEvent.change(within(form).getByLabelText('질문 제목'), { target: { value: '가상 질문' } });
    fireEvent.change(within(form).getByLabelText('질문 내용'), { target: { value: '가상 본문' } });
    fireEvent.submit(form);
    expect(await screen.findByRole('alert')).toHaveTextContent('같은 입력');
    expect(within(form).getByLabelText('질문 내용')).toHaveValue('가상 본문');
    fireEvent.submit(form);
    expect(await screen.findByRole('heading', { name: '가상 질문' })).toBeInTheDocument();
    const posts = vi.mocked(requestData).mock.calls.filter(([, init]) => init?.method === 'POST');
    expect(posts).toHaveLength(2);
    expect(new Headers(posts[0][1]?.headers).get('Idempotency-Key')).toBe(new Headers(posts[1][1]?.headers).get('Idempotency-Key'));
    expect(posts[0][0]).toBe(`/notice-discussion/departments/${D}/questions`);
    expect(JSON.parse(posts[1][1]?.body as string)).toEqual({ title: '가상 질문', body: '가상 본문' });
  });

  it('입력 변경 시 새 멱등 키를 사용하며 성공 응답 오염을 거부한다', async () => {
    vi.mocked(requestData).mockImplementation(async (path, init) => {
      if (init?.method === 'POST') return { ...row, owner_id: 'private-owner' };
      return path.includes('/questions?') ? { items: [], offset: 0, limit: 10 } : [];
    });
    render(<NoticeDiscussionPage departmentId={D} />);
    fireEvent.click(screen.getByRole('button', { name: '학과 질문' }));
    fireEvent.change(screen.getByLabelText('질문 제목'), { target: { value: '질문' } });
    fireEvent.change(screen.getByLabelText('질문 내용'), { target: { value: '내용1' } });
    fireEvent.submit(screen.getByRole('form', { name: '시연 질문 작성·수정' }));
    await screen.findByRole('alert');
    fireEvent.change(screen.getByLabelText('질문 내용'), { target: { value: '내용2' } });
    fireEvent.submit(screen.getByRole('form', { name: '시연 질문 작성·수정' }));
    await waitFor(() => expect(vi.mocked(requestData).mock.calls.filter(([, i]) => i?.method === 'POST')).toHaveLength(2));
    const posts = vi.mocked(requestData).mock.calls.filter(([, i]) => i?.method === 'POST');
    expect(new Headers(posts[0][1]?.headers).get('Idempotency-Key')).not.toBe(new Headers(posts[1][1]?.headers).get('Idempotency-Key'));
    expect(screen.queryByText('private-owner')).toBeNull();
  });

  it('401·403이 오면 화면 전체를 비우고 안전하게 재조회한다', async () => {
    vi.mocked(requestData).mockRejectedValue(new ApiError('FORBIDDEN', 403));
    render(<NoticeDiscussionPage departmentId={D} />);
    expect(await screen.findByText(/현재 접근 권한을 확인하지 못해/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '학과 질문' })).toBeNull();
    expect(screen.getByRole('button', { name: '권한 다시 확인' })).toBeInTheDocument();
  });

  it('학과 변경 시 이전 입력과 선택을 재사용하지 않는다', async () => {
    const view = render(<NoticeDiscussionPage departmentId={D} />);
    fireEvent.click(screen.getByRole('button', { name: '학과 질문' }));
    fireEvent.change(screen.getByLabelText('질문 내용'), { target: { value: '이전 학과 초안' } });
    view.rerender(<NoticeDiscussionPage departmentId={N} />);
    fireEvent.click(screen.getByRole('button', { name: '학과 질문' }));
    expect(screen.getByLabelText('질문 내용')).toHaveValue('');
    expect(screen.queryByText('이전 학과 초안')).toBeNull();
  });

  it('유해 메타데이터·신원·문맥 오염 응답을 거부한다', () => {
    expect(isItem({ ...row, owner_id: 'private' })).toBe(false);
    expect(isItem({ ...row, identity_display_policy: 'OFFICIAL' })).toBe(false);
    expect(isNotice({ ...notice, attachments: [{ ...notice.attachments[0], filename: '../secret.pdf' }] })).toBe(false);
    expect(isNotice({ ...notice, history: [{ ...notice.history[0], revision: 3 }] })).toBe(false);
    expect(isPage({ items: [row], offset: -1, limit: 10 })).toBe(false);
  });
});
