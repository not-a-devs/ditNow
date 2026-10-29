import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import CollaborationFeature from './index';
import type { Comment, Group, PostSummary } from './types';

type Handler = (method: string, path: string, init: RequestInit) => Response | Promise<Response>;

const ok = (data: unknown, status = 200) => new Response(JSON.stringify({ data }), { status });
const fail = (code: string, status: number) =>
  new Response(JSON.stringify({ code, message: 'server-detail', request_id: '12345678-1234-1234-1234-123456789012' }), { status });
const page = <T,>(items: T[]) => ({ items, limit: 20, offset: 0, has_more: false });

function stub(handler: Handler) {
  const fetch = vi.fn((url: string | URL, init: RequestInit = {}) => {
    const parsed = new URL(String(url));
    return Promise.resolve(handler(init.method ?? 'GET', parsed.pathname + parsed.search, init));
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

const posts = (fetch: ReturnType<typeof stub>, suffix: string) =>
  fetch.mock.calls
    .filter(([url, init]) => (init?.method ?? 'GET') === 'POST' && new URL(String(url)).pathname.endsWith(suffix))
    .map(([, init]) => ({ key: (init?.headers as Record<string, string>)['Idempotency-Key'], body: init?.body ? JSON.parse(String(init.body)) : undefined }));

const POST: PostSummary = { id: 'p1', display_name: '익명', title: '알고리즘 스터디 후기', excerpt: '가상 본문', comment_count: 1, created_at: '2026-10-30T00:00:00Z' };
const COMMENT: Comment = {
  id: 'c1', post_id: 'p1', display_name: '익명', body: '<img src=x onerror=alert(1)>', is_mine: false, revision: 1,
  created_at: '2026-10-30T00:00:00Z', updated_at: '2026-10-30T00:00:00Z',
};
const GROUP: Group = {
  id: 'g1', kind: 'study', name: '가상 알고리즘 스터디', description: '', join_mode: 'approval', capacity: 5, member_count: 1,
  status: 'open', origin: 'member_created', source: { kind: 'USER_DEMO', url: null, checked_at: null },
  policy_basis: 'DEMO_DESIGN_DEFAULT', leader: { display_name: '가상학생A' }, my_membership: null, revision: 1,
  created_at: '2026-10-30T00:00:00Z', updated_at: '2026-10-30T00:00:00Z',
};

async function search(q = '알고리즘') {
  fireEvent.change(screen.getByLabelText('검색어'), { target: { value: q } });
  fireEvent.click(screen.getByRole('button', { name: '검색' }));
}

async function openThread() {
  await search();
  fireEvent.click(await screen.findByRole('button', { name: '댓글 보기' }));
  return screen.findByRole('article', { name: '댓글 스레드' });
}

describe('anonymous search and comments', () => {
  it('validates the query locally without a request', async () => {
    const fetch = stub(() => ok(page([])));
    render(<CollaborationFeature />);
    await search('a');
    expect(screen.getByRole('alert')).toHaveTextContent('2~50자');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('shows loading, 503 connection pending, retry, then empty', async () => {
    let resolve!: (r: Response) => void;
    let attempt = 0;
    stub(() => (++attempt === 1 ? new Promise<Response>(r => { resolve = r; }) : ok(page([]))));
    render(<CollaborationFeature />);
    await search();
    expect(screen.getByText('검색 결과 불러오는 중…')).toBeInTheDocument();
    resolve(fail('UNAVAILABLE', 503));
    expect(await screen.findByText(/연결 준비 중입니다/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }));
    expect(await screen.findByText('검색 결과이(가) 없습니다.')).toBeInTheDocument();
  });

  it('renders server text as text and keeps the comment form and key on failure', async () => {
    let commentAttempts = 0;
    const fetch = stub((method, path) => {
      if (path.startsWith('/api/v1/search/')) return ok(page([POST]));
      if (method === 'GET' && path.includes('/comments')) return ok(page([COMMENT]));
      if (method === 'POST' && path.endsWith('/comments')) {
        commentAttempts += 1;
        return commentAttempts < 3 ? fail('INTERNAL', 500) : ok({ ...COMMENT, id: 'c2', body: '새 댓글', is_mine: true }, 201);
      }
      return fail('NOT_FOUND', 404);
    });
    render(<CollaborationFeature />);
    const thread = await openThread();
    expect(await within(thread).findByText('<img src=x onerror=alert(1)>')).toBeInTheDocument();
    expect(thread.querySelector('img')).toBeNull();

    const box = within(thread).getByLabelText('익명 댓글');
    fireEvent.change(box, { target: { value: '첫 댓글' } });
    fireEvent.click(within(thread).getByRole('button', { name: '익명 댓글 등록 요청' }));
    expect(await within(thread).findByRole('alert')).toHaveTextContent('요청을 처리하지 못했습니다.');
    expect(box).toHaveValue('첫 댓글');
    // An unchanged retry reuses the key; editing the text rotates it.
    fireEvent.change(box, { target: { value: '고친 댓글' } });
    fireEvent.click(within(thread).getByRole('button', { name: '익명 댓글 등록 요청' }));
    await waitFor(() => expect(posts(fetch, '/comments')).toHaveLength(2));
    fireEvent.click(within(thread).getByRole('button', { name: '익명 댓글 등록 요청' }));
    await waitFor(() => expect(box).toHaveValue(''));
    const [first, second, third] = posts(fetch, '/comments');
    expect(first.key).not.toBe(second.key);
    expect(second.key).toBe(third.key);
    expect(third.body).toEqual({ body: '고친 댓글' });
  });

  it('refuses an identity-leaking comment payload instead of rendering it', async () => {
    stub((method, path) => {
      if (path.startsWith('/api/v1/search/')) return ok(page([POST]));
      return ok(page([{ ...COMMENT, body: '노출되면 안 됨', author_id: 'user-1' }]));
    });
    render(<CollaborationFeature />);
    const thread = await openThread();
    expect(await within(thread).findByText('서버 응답 형식을 확인할 수 없습니다.')).toBeInTheDocument();
    expect(screen.queryByText('노출되면 안 됨')).not.toBeInTheDocument();
  });

  it('sends a reason-only report and shows success only after the server accepts', async () => {
    let attempt = 0;
    const fetch = stub((method, path) => {
      if (path.startsWith('/api/v1/search/')) return ok(page([POST]));
      if (method === 'GET' && path.includes('/comments')) return ok(page([]));
      if (path === '/api/v1/reports') {
        attempt += 1;
        return attempt === 1 ? fail('CONFLICT', 409) : ok({ id: 'r1', target_type: 'anonymous_post', target_id: 'p1', reason: 'privacy', status: 'submitted', created_at: '2026-10-30T00:00:00Z' }, 201);
      }
      return fail('NOT_FOUND', 404);
    });
    render(<CollaborationFeature />);
    const thread = await openThread();
    fireEvent.change(within(thread).getByLabelText('글 신고 사유'), { target: { value: 'privacy' } });
    fireEvent.click(within(thread).getByRole('button', { name: '글 신고' }));
    expect(await within(thread).findByRole('alert')).toHaveTextContent('충돌');
    expect(within(thread).queryByText(/신고 요청이 접수/)).not.toBeInTheDocument();
    fireEvent.click(within(thread).getByRole('button', { name: '글 신고' }));
    expect(await within(thread).findByText(/신고 요청이 접수되었습니다/)).toBeInTheDocument();
    const sent = posts(fetch, '/reports');
    expect(sent.map(s => s.body)).toEqual([
      { target_type: 'anonymous_post', target_id: 'p1', reason: 'privacy' },
      { target_type: 'anonymous_post', target_id: 'p1', reason: 'privacy' },
    ]);
    expect(sent[0].key).toBe(sent[1].key);
  });

  it('changes the bookmark label only from the server answer', async () => {
    let fails = true;
    stub((method, path) => {
      if (path.startsWith('/api/v1/search/')) return ok(page([POST]));
      if (method === 'PUT') return fails ? fail('UNAVAILABLE', 503) : ok({ post_id: 'p1', bookmarked: true });
      return fail('NOT_FOUND', 404);
    });
    render(<CollaborationFeature />);
    await search();
    fireEvent.click(await screen.findByRole('button', { name: '북마크' }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '북마크' })).toHaveAttribute('aria-pressed', 'false');
    fails = false;
    fireEvent.click(screen.getByRole('button', { name: '북마크' }));
    expect(await screen.findByRole('button', { name: '북마크 해제' })).toHaveAttribute('aria-pressed', 'true');
  });
});

describe('auth failures remove personal views', () => {
  it.each([[401, 'UNAUTHORIZED', '로그인이 필요합니다.'], [403, 'FORBIDDEN', '커뮤니티 참여 권한이 확인되지 않았습니다.']])(
    'a %s on my bookmarks unmounts every panel and shows the parent notice',
    async (status, code, message) => {
      let denied = true;
      stub((_m, path) => {
        if (path.startsWith('/api/v1/me/bookmarks')) return denied ? fail(code, status) : ok(page([]));
        return ok(page([]));
      });
      render(<CollaborationFeature />);
      fireEvent.click(screen.getByRole('tab', { name: '내 북마크·신고' }));
      expect(await screen.findByText(message)).toBeInTheDocument();
      expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
      expect(screen.queryByText('내 신고 요청')).not.toBeInTheDocument();
      denied = false;
      fireEvent.click(screen.getByRole('button', { name: '다시 시도' }));
      expect(await screen.findByRole('tablist')).toBeInTheDocument();
    },
  );
});

describe('groups and team space', () => {
  it('labels demo policy and provenance and never links unsafe official URLs', async () => {
    const official = { ...GROUP, id: 'g2', origin: 'catalog' as const, source: { kind: 'OFFICIAL_PUBLIC' as const, url: 'javascript:alert(1)', checked_at: '2026-10-29T00:00:00Z' } };
    stub((_m, path) => {
      if (path.startsWith('/api/v1/groups?')) return ok(page([GROUP, official]));
      if (path === '/api/v1/groups/g2') return ok(official);
      return ok(GROUP);
    });
    render(<CollaborationFeature />);
    fireEvent.click(screen.getByRole('tab', { name: '스터디·동아리' }));
    expect(await screen.findByText(/학교 동아리 규정이 아닙니다/)).toBeInTheDocument();
    fireEvent.click((await screen.findAllByRole('button', { name: '열기' }))[1]);
    const detail = await screen.findByRole('article', { name: '모임 상세' });
    expect(within(detail).getByText('출처 확인 필요')).toBeInTheDocument();
    expect(detail.querySelector('a')).toBeNull();
  });

  it('reuses the join key after a 503 and shows pending only from the server', async () => {
    let joins = 0;
    let mine: Group['my_membership'] = null;
    const fetch = stub((method, path) => {
      if (path.startsWith('/api/v1/groups?')) return ok(page([GROUP]));
      if (method === 'POST' && path.endsWith('/join-requests')) {
        joins += 1;
        if (joins === 1) return fail('UNAVAILABLE', 503);
        mine = { id: 'm1', role: 'member', status: 'pending', revision: 1 };
        return ok(mine, 201);
      }
      return ok({ ...GROUP, my_membership: mine });
    });
    render(<CollaborationFeature />);
    fireEvent.click(screen.getByRole('tab', { name: '스터디·동아리' }));
    fireEvent.click(await screen.findByRole('button', { name: '열기' }));
    const detail = await screen.findByRole('article', { name: '모임 상세' });
    fireEvent.click(within(detail).getByRole('button', { name: '참여 요청' }));
    expect(await within(detail).findByRole('alert')).toHaveTextContent('연결 준비 중');
    expect(within(detail).queryByText(/승인 대기/)).not.toBeInTheDocument();
    fireEvent.click(within(detail).getByRole('button', { name: '참여 요청' }));
    expect(await screen.findByText(/내 상태: 승인 대기/)).toBeInTheDocument();
    const [first, second] = posts(fetch, '/join-requests');
    expect(first.key).toBe(second.key);
    expect(screen.queryByRole('region', { name: '팀 활동 공간' })).not.toBeInTheDocument();
  });

  it('shows join requests to the leader and the members-only space', async () => {
    const leader = { ...GROUP, my_membership: { id: 'm0', role: 'leader' as const, status: 'active' as const, revision: 1 } };
    const fetch = stub((method, path) => {
      if (path.startsWith('/api/v1/groups?')) return ok(page([leader]));
      if (path.startsWith('/api/v1/groups/g1/join-requests?')) return ok(page([{ id: 'm1', group_id: 'g1', applicant: { display_name: '가상학생B' }, status: 'pending', revision: 1, created_at: '2026-10-30T00:00:00Z' }]));
      if (path.endsWith('/decision')) return ok({ id: 'm1', group_id: 'g1', applicant: { display_name: '가상학생B' }, status: 'active', revision: 2, created_at: '2026-10-30T00:00:00Z' });
      if (path.startsWith('/api/v1/groups/g1/space/posts')) return ok(page([{ id: 's1', group_id: 'g1', author: { display_name: '가상학생A' }, is_mine: true, body: '회의 기록', revision: 1, created_at: '2026-10-30T00:00:00Z' }]));
      if (method === 'GET') return ok(leader);
      return fail('NOT_FOUND', 404);
    });
    render(<CollaborationFeature />);
    fireEvent.click(screen.getByRole('tab', { name: '스터디·동아리' }));
    fireEvent.click(await screen.findByRole('button', { name: '열기' }));
    const requests = await screen.findByRole('region', { name: '참여 요청' });
    expect(await within(requests).findByText('가상학생B')).toBeInTheDocument();
    fireEvent.click(within(requests).getByRole('button', { name: '승인' }));
    await waitFor(() => expect(posts(fetch, '/decision')[0]?.body).toEqual({ decision: 'approve', revision: 1 }));
    const space = await screen.findByRole('region', { name: '팀 활동 공간' });
    expect(await within(space).findByText('회의 기록')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '탈퇴' })).not.toBeInTheDocument();
  });

  it('a 403 during a group action removes the personal views', async () => {
    stub((method, path) => {
      if (path.startsWith('/api/v1/groups?')) return ok(page([GROUP]));
      if (method === 'POST') return fail('FORBIDDEN', 403);
      return ok(GROUP);
    });
    render(<CollaborationFeature />);
    fireEvent.click(screen.getByRole('tab', { name: '스터디·동아리' }));
    fireEvent.click(await screen.findByRole('button', { name: '열기' }));
    fireEvent.click(await screen.findByRole('button', { name: '참여 요청' }));
    expect(await screen.findByText('커뮤니티 참여 권한이 확인되지 않았습니다.')).toBeInTheDocument();
    expect(screen.queryByRole('article', { name: '모임 상세' })).not.toBeInTheDocument();
  });
});
