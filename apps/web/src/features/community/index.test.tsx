import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import CommunityFeature from './index';
import type { AnonymousPost, Recruitment } from './types';

type Handler = (url: string, init: RequestInit) => Response | Promise<Response>;

const ok = (data: unknown, status = 200) => new Response(JSON.stringify({ data }), { status });
const fail = (code: string, status: number) =>
  new Response(JSON.stringify({ code, message: 'server-detail', request_id: '12345678-1234-1234-1234-123456789012' }), { status });
const page = <T,>(items: T[]) => ({ items, limit: 20, offset: 0, has_more: false });

function stub(handler: Handler) {
  const fetch = vi.fn((url: string | URL, init: RequestInit = {}) => Promise.resolve(handler(String(url), init)));
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

const sent = (fetch: ReturnType<typeof stub>, method: string) =>
  fetch.mock.calls.filter(([, init]) => (init?.method ?? 'GET') === method).map(([url, init]) => ({
    url: String(url),
    headers: (init?.headers ?? {}) as Record<string, string>,
    body: init?.body ? JSON.parse(String(init.body)) : undefined,
  }));

const POST_ROW: AnonymousPost = {
  id: 'p1', display_name: '익명', title: '다른 사람 글', body: '<b>본문</b>', status: 'active',
  comment_count: 0, is_mine: false, revision: 1, created_at: '2026-10-30T00:00:00Z', updated_at: '2026-10-30T00:00:00Z',
};

const RECRUITMENT: Recruitment = {
  id: 'r1', owner: { display_name: '가상학생A' }, is_mine: true, title: '공모전 팀원', body: '백엔드 구해요',
  field: '개발', roles: ['백엔드', '디자인'], capacity: 3, accepted_count: 0, deadline_at: '2099-01-01T00:00:00Z',
  status: 'open', opportunity_id: null, revision: 2, created_at: '2026-10-30T00:00:00Z', updated_at: '2026-10-30T00:00:00Z',
};

describe('community list states', () => {
  it('shows loading and keeps submit disabled until the server answers', async () => {
    let resolve!: (response: Response) => void;
    stub(() => new Promise<Response>(r => { resolve = r; }));
    render(<CommunityFeature />);
    expect(screen.getByText('게시글 불러오는 중…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '익명으로 등록 요청' })).toBeDisabled();
    resolve(ok(page([])));
    expect(await screen.findByText('게시글이(가) 아직 없습니다.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '익명으로 등록 요청' })).toBeEnabled();
  });

  it('shows connection pending on 503 and recovers on retry', async () => {
    let attempt = 0;
    const fetch = stub(() => (++attempt === 1 ? fail('UNAVAILABLE', 503) : ok(page([POST_ROW]))));
    render(<CommunityFeature />);
    expect(await screen.findByText(/연결 준비 중입니다/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '익명으로 등록 요청' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }));
    expect(await screen.findByText('다른 사람 글')).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(2);
    // Server text is rendered as text, never as markup; no edit controls on others' posts.
    expect(screen.getByText('<b>본문</b>')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '수정' })).not.toBeInTheDocument();
  });

  it('asks for login on 401 without showing server details', async () => {
    stub(() => fail('UNAUTHORIZED', 401));
    render(<CommunityFeature />);
    expect(await screen.findByText('로그인이 필요합니다.')).toBeInTheDocument();
    expect(screen.queryByText(/server-detail/)).not.toBeInTheDocument();
  });

  it('shows a generic error with request id on 500', async () => {
    stub(() => fail('INTERNAL', 500));
    render(<CommunityFeature />);
    expect(await screen.findByText('요청을 처리하지 못했습니다.')).toBeInTheDocument();
    expect(screen.getByText(/12345678-1234-1234-1234-123456789012/)).toBeInTheDocument();
  });
});

describe('anonymous post submission retry', () => {
  it('reuses the Idempotency-Key for an unchanged retry and rotates it after an edit', async () => {
    let posts = 0;
    const fetch = stub((url, init) => {
      if (init.method !== 'POST') return ok(page([]));
      posts += 1;
      if (posts <= 2) throw new TypeError('network down');
      return ok({ ...POST_ROW, is_mine: true }, 201);
    });
    render(<CommunityFeature />);
    const submit = await screen.findByRole('button', { name: '익명으로 등록 요청' });
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.change(screen.getByLabelText('제목'), { target: { value: '새 글 제목' } });
    fireEvent.change(screen.getByLabelText('본문'), { target: { value: '본문' } });

    fireEvent.click(submit);
    expect(await screen.findByRole('alert')).toHaveTextContent('연결 준비 중입니다');
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.click(submit);
    await waitFor(() => expect(sent(fetch, 'POST')).toHaveLength(2));
    await waitFor(() => expect(submit).toBeEnabled());
    expect(screen.getByLabelText('제목')).toHaveValue('새 글 제목');

    fireEvent.change(screen.getByLabelText('제목'), { target: { value: '바뀐 제목' } });
    fireEvent.click(submit);
    await waitFor(() => expect(screen.getByLabelText('제목')).toHaveValue(''));

    const [first, retry, edited] = sent(fetch, 'POST');
    expect(first.url).toBe(`${window.location.origin}/api/v1/anonymous-posts`);
    expect(first.headers['Idempotency-Key']).toBeTruthy();
    expect(retry.headers['Idempotency-Key']).toBe(first.headers['Idempotency-Key']);
    expect(edited.headers['Idempotency-Key']).not.toBe(first.headers['Idempotency-Key']);
    expect(edited.body).toEqual({ title: '바뀐 제목', body: '본문' });
  });

  it('blocks invalid input locally without calling the server', async () => {
    const fetch = stub(() => ok(page([])));
    render(<CommunityFeature />);
    const submit = await screen.findByRole('button', { name: '익명으로 등록 요청' });
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.change(screen.getByLabelText('제목'), { target: { value: '가' } });
    fireEvent.click(submit);
    expect(await screen.findByText('제목은 2~120자로 입력하세요.')).toBeInTheDocument();
    expect(sent(fetch, 'POST')).toHaveLength(0);
  });
});

describe('recruitment owner edit', () => {
  it('sends only changed fields with the current revision and offers no delete', async () => {
    const fetch = stub((url, init) =>
      init.method === 'PATCH' ? ok({ ...RECRUITMENT, capacity: 5, revision: 3 }) : ok(page([RECRUITMENT])));
    render(<CommunityFeature />);
    fireEvent.click(screen.getByRole('tab', { name: '실명 모집' }));
    expect(await screen.findByText('공모전 팀원')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /삭제/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '수정' }));
    const form = screen.getByRole('form', { name: '모집글 수정' });
    fireEvent.click(within(form).getByRole('button', { name: '수정 요청' }));
    expect(await within(form).findByText('변경된 내용이 없습니다.')).toBeInTheDocument();
    expect(sent(fetch, 'PATCH')).toHaveLength(0);

    fireEvent.change(within(form).getByLabelText('총 인원 (모집자 포함)'), { target: { value: '5' } });
    fireEvent.click(within(form).getByRole('button', { name: '수정 요청' }));
    await waitFor(() => expect(sent(fetch, 'PATCH')).toHaveLength(1));
    const [patch] = sent(fetch, 'PATCH');
    expect(patch.url).toBe(`${window.location.origin}/api/v1/recruitments/r1`);
    expect(patch.body).toEqual({ revision: 2, capacity: 5 });
    await waitFor(() => expect(screen.queryByRole('form', { name: '모집글 수정' })).not.toBeInTheDocument());
  });

  it('keeps the edit form open and explains a 409 conflict', async () => {
    stub((url, init) => (init.method === 'PATCH' ? fail('CONFLICT', 409) : ok(page([RECRUITMENT]))));
    render(<CommunityFeature />);
    fireEvent.click(screen.getByRole('tab', { name: '실명 모집' }));
    fireEvent.click(await screen.findByRole('button', { name: '수정' }));
    const form = screen.getByRole('form', { name: '모집글 수정' });
    fireEvent.change(within(form).getByLabelText('분야'), { target: { value: '디자인' } });
    fireEvent.click(within(form).getByRole('button', { name: '수정 요청' }));
    expect(await within(form).findByText(/다른 변경과 충돌했습니다/)).toBeInTheDocument();
  });

  it('hides edit and close for recruitments that are not mine', async () => {
    stub(() => ok(page([{ ...RECRUITMENT, is_mine: false }])));
    render(<CommunityFeature />);
    fireEvent.click(screen.getByRole('tab', { name: '실명 모집' }));
    expect(await screen.findByText('공모전 팀원')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '수정' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '모집 마감' })).not.toBeInTheDocument();
  });
});
