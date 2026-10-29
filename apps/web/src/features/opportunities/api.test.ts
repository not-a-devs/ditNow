// Uses the real shared requestData with only fetch stubbed, so the final URL is what the browser
// would request. Guards against the /api/v1/api/v1 double prefix.
import { describe, expect, it, vi } from 'vitest';
import * as api from './api';
import type { CheckItem } from './types';

const OID = '00000000-0000-4000-8000-000000000001';
const CHECK: CheckItem = { id: '00000000-0000-4000-8000-0000000000c1', text: 'x', sort_order: 0, completed_at: null, revision: 3 };

function stubFetch() {
  const fetch = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ data: {} }), { status: 200 }));
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

const calls: Array<[string, () => Promise<unknown>, string, string]> = [
  ['list', () => api.listOpportunities({ kind: 'contest', q: ' 공모 ', openOnly: true }), 'GET', '/api/v1/opportunities?kind=contest&q=%EA%B3%B5%EB%AA%A8&open_only=true'],
  ['detail', () => api.getOpportunity(OID), 'GET', `/api/v1/opportunities/${OID}`],
  ['saved list', () => api.listSaved(), 'GET', '/api/v1/me/saved-opportunities'],
  ['save', () => api.saveOpportunity(OID), 'PUT', `/api/v1/me/saved-opportunities/${OID}`],
  ['update', () => api.updateSaved(OID, 2, { status: 'preparing' }), 'PATCH', `/api/v1/me/saved-opportunities/${OID}`],
  ['delete', () => api.deleteSaved(OID, 2), 'DELETE', `/api/v1/me/saved-opportunities/${OID}`],
  ['add check', () => api.addCheck(OID, 'x', 0, 'chk-key-0001'), 'POST', `/api/v1/me/saved-opportunities/${OID}/checks`],
  ['update check', () => api.updateCheck(OID, CHECK, { completed: true }), 'PATCH', `/api/v1/me/saved-opportunities/${OID}/checks/${CHECK.id}`],
  ['delete check', () => api.deleteCheck(OID, CHECK), 'DELETE', `/api/v1/me/saved-opportunities/${OID}/checks/${CHECK.id}`],
];

describe('opportunities API client through the shared transport', () => {
  it.each(calls)('%s hits the default base exactly once', async (_name, call, method, path) => {
    const fetch = stubFetch();
    await call();
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe(`${window.location.origin}${path}`);
    expect(new URL(url).pathname).not.toContain('/api/v1/api/v1');
    expect(init.method ?? 'GET').toBe(method);
  });

  it('respects a configured absolute API base without doubling the prefix', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://api.example.test/api/v1');
    const fetch = stubFetch();
    await api.listSaved();
    expect(fetch.mock.calls[0][0]).toBe('https://api.example.test/api/v1/me/saved-opportunities');
  });

  it('sends If-Match revision and the caller-provided Idempotency-Key unchanged', async () => {
    const fetch = stubFetch();
    await api.updateCheck(OID, CHECK, { completed: true });
    await api.addCheck(OID, '추천서', 4, 'chk-same-key');
    expect(fetch.mock.calls[0][1].headers['If-Match']).toBe('3');
    expect(fetch.mock.calls[1][1].headers['Idempotency-Key']).toBe('chk-same-key');
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ text: '추천서', sort_order: 4 });
  });

  it('creates a fresh key per call', () => {
    expect(api.newIdempotencyKey()).not.toBe(api.newIdempotencyKey());
    expect(api.newIdempotencyKey()).toMatch(/^chk-[A-Za-z0-9-]{8,96}$/);
  });
});
