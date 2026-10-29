import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../lib/api';
import { SecureContextRequiredError, collaborationApi, createKeyTracker, describeError } from './api';
import { isBookmarkState, isComment, isGroup, isPostSummary, safeLink } from './guards';

const PAGE = { items: [], limit: 20, offset: 0, has_more: false };
const POST = { id: 'p1', display_name: '익명', title: 't', excerpt: 'e', comment_count: 0, bookmarked: false, created_at: '2026-10-30T00:00:00Z' };
const COMMENT = {
  id: 'c1', post_id: 'p1', display_name: '익명', body: 'x', is_mine: true, revision: 1,
  created_at: '2026-10-30T00:00:00Z', updated_at: '2026-10-30T00:00:00Z',
};
const MEMBERSHIP = { id: 'm1', role: 'member', status: 'pending', revision: 1 };
const GROUP = {
  id: 'g1', kind: 'study', name: '가상 스터디', description: '', join_mode: 'approval', capacity: 5, member_count: 1,
  status: 'open', origin: 'member_created', source: { kind: 'USER_DEMO', url: null, checked_at: null },
  policy_basis: 'DEMO_DESIGN_DEFAULT', leader: { display_name: '가상학생A' }, my_membership: null, revision: 1,
  created_at: '2026-10-30T00:00:00Z', updated_at: '2026-10-30T00:00:00Z',
};
const REQUEST = { id: 'm1', group_id: 'g1', applicant: { display_name: '가상학생B' }, status: 'active', revision: 2, created_at: '2026-10-30T00:00:00Z' };
const SPACE = { id: 's1', group_id: 'g1', author: { display_name: '가상학생A' }, is_mine: true, body: 'x', revision: 1, created_at: '2026-10-30T00:00:00Z' };
const REPORT = { id: 'r1', target_type: 'anonymous_post', target_id: 'p1', reason: 'spam', status: 'submitted', created_at: '2026-10-30T00:00:00Z' };

// Exercises the real shared client (../../lib/api); only fetch is stubbed.
function stubFetch() {
  const fetch = vi.fn(async (url: string | URL, init: RequestInit = {}) => {
    const path = new URL(String(url)).pathname;
    const method = init.method ?? 'GET';
    let data: unknown = PAGE;
    if (method === 'DELETE' && path.includes('/bookmarks/')) data = { post_id: 'p1', bookmarked: false };
    else if (method === 'DELETE') data = { id: 'x', deleted: true };
    else if (method === 'PUT') data = { post_id: 'p1', bookmarked: true };
    else if (path.endsWith('/comments') && method === 'POST') data = COMMENT;
    else if (path.endsWith('/reports') && method === 'POST') data = REPORT;
    else if (path.endsWith('/join-requests') && method === 'POST') data = MEMBERSHIP;
    else if (path.endsWith('/leave')) data = MEMBERSHIP;
    else if (path.endsWith('/decision')) data = REQUEST;
    else if (path.endsWith('/space/posts') && method === 'POST') data = SPACE;
    else if (path.endsWith('/groups') && method === 'POST') data = GROUP;
    else if (/\/groups\/[^/]+$/.test(path)) data = GROUP;
    return new Response(JSON.stringify({ data }), { status: method === 'POST' ? 201 : 200 });
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

const calls = (fetch: ReturnType<typeof stubFetch>) =>
  fetch.mock.calls.map(([url, init]) => ({ url: String(url), init: (init ?? {}) as RequestInit }));

describe('collaboration API paths through the shared client', () => {
  it('adds the /api/v1 prefix exactly once for every endpoint', async () => {
    const fetch = stubFetch();
    const api = collaborationApi;
    await api.searchPosts('알고리즘 스터디');
    await api.listComments('p1');
    await api.createComment('p1', '댓글', 'key-00000001');
    await api.deleteComment('p1', 'c1', 2);
    await api.listBookmarks();
    await api.addBookmark('p1');
    await api.removeBookmark('p1');
    await api.createReport('anonymous_post', 'p1', 'spam', 'key-00000002');
    await api.listReports();
    await api.listGroups('club', '밴드');
    await api.getGroup('g1');
    await api.createGroup({ kind: 'study', name: '가상 스터디', description: '', join_mode: 'approval', capacity: 5 }, 'key-00000003');
    await api.requestJoin('g1', 'key-00000004');
    await api.listJoinRequests('g1');
    await api.decideJoin('g1', 'm1', 'approve', 1);
    await api.leaveGroup('g1', 2);
    await api.listSpacePosts('g1');
    await api.createSpacePost('g1', '기록', 'key-00000005');
    await api.deleteSpacePost('g1', 's1', 1);
    const o = window.location.origin;
    expect(calls(fetch).map(c => `${c.init.method ?? 'GET'} ${c.url}`)).toEqual([
      `GET ${o}/api/v1/search/anonymous-posts?q=%EC%95%8C%EA%B3%A0%EB%A6%AC%EC%A6%98+%EC%8A%A4%ED%84%B0%EB%94%94&limit=20`,
      `GET ${o}/api/v1/anonymous-posts/p1/comments?limit=50`,
      `POST ${o}/api/v1/anonymous-posts/p1/comments`,
      `DELETE ${o}/api/v1/anonymous-posts/p1/comments/c1?revision=2`,
      `GET ${o}/api/v1/me/bookmarks?limit=50`,
      `PUT ${o}/api/v1/me/bookmarks/p1`,
      `DELETE ${o}/api/v1/me/bookmarks/p1`,
      `POST ${o}/api/v1/reports`,
      `GET ${o}/api/v1/me/reports?limit=50`,
      `GET ${o}/api/v1/groups?kind=club&q=%EB%B0%B4%EB%93%9C&limit=20`,
      `GET ${o}/api/v1/groups/g1`,
      `POST ${o}/api/v1/groups`,
      `POST ${o}/api/v1/groups/g1/join-requests`,
      `GET ${o}/api/v1/groups/g1/join-requests?limit=50`,
      `POST ${o}/api/v1/groups/g1/join-requests/m1/decision`,
      `POST ${o}/api/v1/groups/g1/membership/leave`,
      `GET ${o}/api/v1/groups/g1/space/posts?limit=50`,
      `POST ${o}/api/v1/groups/g1/space/posts`,
      `DELETE ${o}/api/v1/groups/g1/space/posts/s1?revision=1`,
    ]);
    for (const { url } of calls(fetch)) expect(url).not.toContain('/api/v1/api/v1');
  });

  it('respects a configured absolute API base without doubling the prefix', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://api.example.test/api/v1');
    const fetch = stubFetch();
    await collaborationApi.listReports();
    expect(calls(fetch)[0].url).toBe('https://api.example.test/api/v1/me/reports?limit=50');
  });

  it.each([
    ['.'], ['..'], ['../me/reports'], ['%2e%2e'], ['%2E'], ['a%2Fb'], ['a/b'], ['a\\b'], ['a b'], [''], ['x'.repeat(65)],
  ])('refuses the path id %j before any request so it cannot change the route', async bad => {
    const fetch = stubFetch();
    await expect(collaborationApi.listComments(bad)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    await expect(collaborationApi.requestJoin(bad, 'key-00000001')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    await expect(collaborationApi.createSpacePost(bad, 'x', 'key-00000002')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    await expect(collaborationApi.deleteComment('p1', bad, 1)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    await expect(collaborationApi.decideJoin('g1', bad, 'approve', 1)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    expect(fetch).not.toHaveBeenCalled();
  });

  it('accepts server-pattern ids up to 64 characters', async () => {
    const fetch = stubFetch();
    const longest = 'A'.repeat(32) + 'z_9-'.repeat(8);
    await collaborationApi.listComments(longest);
    await collaborationApi.getGroup('3f2a_b-C');
    expect(calls(fetch).map(c => new URL(c.url).pathname)).toEqual([
      `/api/v1/anonymous-posts/${longest}/comments`,
      '/api/v1/groups/3f2a_b-C',
    ]);
  });

  it.each([['.'], ['..'], ['a/b'], ['%2e']])('response guards refuse the id %j', bad => {
    expect(isComment({ ...COMMENT, id: bad })).toBe(false);
    expect(isComment({ ...COMMENT, post_id: bad })).toBe(false);
    expect(isGroup({ ...GROUP, id: bad })).toBe(false);
    expect(isPostSummary({ ...POST, id: bad })).toBe(false);
    expect(isBookmarkState({ post_id: bad, bookmarked: true })).toBe(false);
  });

  it('checks the anonymous bookmark state with an exact key set', () => {
    expect(isBookmarkState({ post_id: 'p1', bookmarked: true })).toBe(true);
    expect(isBookmarkState({ post_id: 'p1', bookmarked: true, user_id: 'u1' })).toBe(false);
    expect(isBookmarkState({ post_id: 'p1', bookmarked: true, display_name: '가상학생B' })).toBe(false);
    expect(isPostSummary(POST)).toBe(true);
    expect(isPostSummary({ ...POST, author_id: 'u1' })).toBe(false);
    expect(isPostSummary({ ...POST, bookmarked: 'yes' })).toBe(false);
  });

  it('sends Idempotency-Key only on creates and a reason-only report body', async () => {
    const fetch = stubFetch();
    await collaborationApi.createReport('anonymous_comment', 'c1', 'privacy', 'key-00000009');
    await collaborationApi.decideJoin('g1', 'm1', 'reject', 3);
    await collaborationApi.requestJoin('g1', 'key-00000010');
    const [report, decision, join] = calls(fetch);
    expect(report.init.headers).toMatchObject({ 'Idempotency-Key': 'key-00000009' });
    expect(JSON.parse(String(report.init.body))).toEqual({ target_type: 'anonymous_comment', target_id: 'c1', reason: 'privacy' });
    expect(decision.init.headers).not.toHaveProperty('Idempotency-Key');
    expect(JSON.parse(String(decision.init.body))).toEqual({ decision: 'reject', revision: 3 });
    expect(join.init.headers).toEqual({ 'Idempotency-Key': 'key-00000010' });
    expect(join.init.body).toBeUndefined();
  });

  it('rejects malformed or identity-leaking responses at runtime', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ data: { ...COMMENT, author_id: 'u1' } }), { status: 201 })));
    await expect(collaborationApi.createComment('p1', 'x', 'key-00000001')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ data: { items: 'no' } }), { status: 200 })));
    await expect(collaborationApi.listGroups()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    expect(isComment(COMMENT)).toBe(true);
    expect(isGroup({ ...GROUP, source: { kind: 'OFFICIAL', url: null, checked_at: null } })).toBe(false);
  });
});

describe('idempotency key tracker', () => {
  it('reuses the key for an unchanged retry and rotates on change or reset', () => {
    let n = 0;
    const keys = createKeyTracker(() => `k${++n}`);
    expect(keys.keyFor({ text: 'a' })).toBe('k1');
    expect(keys.keyFor({ text: 'a' })).toBe('k1');
    expect(keys.keyFor({ text: 'b' })).toBe('k2');
    keys.reset();
    expect(keys.keyFor({ text: 'b' })).toBe('k3');
  });

  it('defaults to random UUIDs accepted by the server key pattern', () => {
    expect(createKeyTracker().keyFor({})).toMatch(/^[!-~]{8,128}$/);
  });

  it.each([[{}], [undefined]])('refuses to invent a key without crypto.randomUUID (%o)', crypto => {
    vi.stubGlobal('crypto', crypto);
    const keys = createKeyTracker();
    expect(() => keys.keyFor({ text: 'a' })).toThrow(SecureContextRequiredError);
    // Nothing weak was cached for a later retry either.
    expect(() => keys.keyFor({ text: 'a' })).toThrow(SecureContextRequiredError);
    const issue = describeError(new SecureContextRequiredError());
    expect(issue).toEqual({ kind: 'error', message: expect.stringContaining('보안 컨텍스트가 필요합니다') });
    expect(issue.message).not.toMatch(/로그인|서버/);
  });
});

describe('describeError and safeLink', () => {
  it.each([
    [new ApiError('UNAUTHORIZED', 401), 'unauthenticated'],
    [new ApiError('FORBIDDEN', 403), 'forbidden'],
    [new ApiError('UNAVAILABLE', 503), 'unavailable'],
    [new ApiError('NETWORK', 0), 'unavailable'],
    [new ApiError('NOT_FOUND', 404), 'error'],
    [new ApiError('CONFLICT', 409), 'error'],
    [new ApiError('INVALID_RESPONSE', 200), 'error'],
    [new Error('boom'), 'unavailable'],
  ])('maps %o to %s', (error, kind) => {
    expect(describeError(error).kind).toBe(kind);
  });

  it.each([
    ['https://www.dit.ac.kr/kr/index.php?pCode=a', 'https://www.dit.ac.kr/kr/index.php?pCode=a'],
    ['http://www.dit.ac.kr/', null],
    ['javascript:alert(1)', null],
    ['https://u:p@www.dit.ac.kr/', null],
    ['https://www.dit.ac.kr/#x', null],
    [null, null],
  ])('safeLink(%s)', (value, expected) => {
    expect(safeLink(value)).toBe(expected);
  });
});
