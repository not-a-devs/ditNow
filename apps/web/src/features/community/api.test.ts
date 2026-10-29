import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../lib/api';
import { communityApi, createKeyTracker, describeError } from './api';

// Exercises the real shared client (../../lib/api); only fetch is stubbed.
function stubFetch() {
  const fetch = vi.fn().mockImplementation(async () =>
    new Response(JSON.stringify({ data: { items: [], limit: 20, offset: 0, has_more: false } }), { status: 200 }));
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

const calls = (fetch: ReturnType<typeof vi.fn>) =>
  fetch.mock.calls.map(([url, init]) => ({ url: String(url), init: init as RequestInit }));

describe('community API paths through the shared client', () => {
  it('adds the /api/v1 prefix exactly once for every endpoint', async () => {
    const fetch = stubFetch();
    await communityApi.listPosts();
    await communityApi.createPost({ title: '제목', body: '본문' }, 'key-1');
    await communityApi.updatePost('p1', 2, { body: 'x' });
    await communityApi.deletePost('p1', 3);
    await communityApi.listRecruitments();
    await communityApi.createRecruitment({ title: '모집', body: 'b', field: '개발', roles: ['백엔드'], capacity: 3, deadline_at: '2030-01-01T00:00:00.000Z' }, 'key-2');
    await communityApi.updateRecruitment('r1', 4, { capacity: 5 });
    await communityApi.closeRecruitment('r1', 5);
    const origin = window.location.origin;
    expect(calls(fetch).map(c => `${c.init.method ?? 'GET'} ${c.url}`)).toEqual([
      `GET ${origin}/api/v1/anonymous-posts?limit=20`,
      `POST ${origin}/api/v1/anonymous-posts`,
      `PATCH ${origin}/api/v1/anonymous-posts/p1`,
      `DELETE ${origin}/api/v1/anonymous-posts/p1?revision=3`,
      `GET ${origin}/api/v1/recruitments?limit=20`,
      `POST ${origin}/api/v1/recruitments`,
      `PATCH ${origin}/api/v1/recruitments/r1`,
      `POST ${origin}/api/v1/recruitments/r1/close`,
    ]);
    for (const { url } of calls(fetch)) expect(url).not.toContain('/api/v1/api/v1');
  });

  it('respects a configured absolute API base without doubling the prefix', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://api.example.test/api/v1');
    const fetch = stubFetch();
    await communityApi.listRecruitments();
    expect(calls(fetch)[0].url).toBe('https://api.example.test/api/v1/recruitments?limit=20');
  });

  it('sends Idempotency-Key only on create requests', async () => {
    const fetch = stubFetch();
    await communityApi.createPost({ title: '제목', body: '본문' }, 'key-1');
    await communityApi.updatePost('p1', 1, { body: 'x' });
    const [create, update] = calls(fetch);
    expect(create.init.headers).toMatchObject({ 'Idempotency-Key': 'key-1', 'Content-Type': 'application/json' });
    expect(JSON.parse(String(create.init.body))).toEqual({ title: '제목', body: '본문' });
    expect(update.init.headers).not.toHaveProperty('Idempotency-Key');
    expect(JSON.parse(String(update.init.body))).toEqual({ revision: 1, body: 'x' });
  });
});

describe('idempotency key tracker', () => {
  it('reuses the key for an unchanged retry and rotates on change or reset', () => {
    let n = 0;
    const keys = createKeyTracker(() => `k${++n}`);
    expect(keys.keyFor({ title: 'a' })).toBe('k1');
    expect(keys.keyFor({ title: 'a' })).toBe('k1');
    expect(keys.keyFor({ title: 'b' })).toBe('k2');
    keys.reset();
    expect(keys.keyFor({ title: 'b' })).toBe('k3');
  });

  it('defaults to random UUIDs', () => {
    expect(createKeyTracker().keyFor({})).toMatch(/^[0-9a-f-]{36}$/);
  });
});

describe('describeError', () => {
  it.each([
    [new ApiError('UNAUTHORIZED', 401), 'unauthenticated'],
    [new ApiError('FORBIDDEN', 403), 'forbidden'],
    [new ApiError('UNAVAILABLE', 503), 'unavailable'],
    [new ApiError('NETWORK', 0), 'unavailable'],
    [new ApiError('CONFLICT', 409), 'error'],
    [new ApiError('INTERNAL', 500), 'error'],
  ])('maps %o to %s', (error, kind) => {
    expect(describeError(error).kind).toBe(kind);
  });
});
