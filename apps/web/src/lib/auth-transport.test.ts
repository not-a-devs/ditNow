import { afterEach, describe, expect, it, vi } from 'vitest';
import { registerAuthentication, requestData, requestSessionLogout, type AuthenticationBridge } from './api';
import { isCurrentUser } from '../features/auth/MemoryAuth';
let release: (() => void) | undefined;
afterEach(() => { release?.(); release = undefined; vi.unstubAllEnvs(); });
const response = (data: unknown, status = 200) => new Response(JSON.stringify(status === 200 ? { data } : { code: 'UNAUTHORIZED', message: 'private-secret' }), { status });
function owner(verified = true) {
  let session = { generation: 1, token: 'token.A' as string | null, verified };
  const denied = vi.fn(); const bridge: AuthenticationBridge = { read: () => session, denied };
  release = registerAuthentication(bridge);
  return { denied, change: () => { session = { generation: 2, token: 'token.B', verified: true }; } };
}
describe('single memory authentication transport', () => {
  it.each(['/anonymous-posts/../health', '/anonymous-posts/./id', '/recruitments/../opportunities'])('rejects literal path normalization before injecting credentials: %s', async path => {
    owner(); const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    await expect(requestData(path)).rejects.toMatchObject({ code: 'CONFIGURATION' }); expect(fetch).not.toHaveBeenCalled();
  });
  it('does not invent an academic year cap and still rejects unsafe numbers', () => {
    const current = { user_id: '10000000-0000-4000-8000-000000000001', display_name: 'DEMO', record_source: 'DEMO', department_id: '20000000-0000-4000-8000-000000000001', department_code: 'DEMO', academic_year: 21, community_access: true };
    expect(isCurrentUser(current)).toBe(true);
    for (const academic_year of [0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1]) expect(isCurrentUser({ ...current, academic_year })).toBe(false);
  });
  it('injects only protected paths, preserves API prefix, strips caller credentials', async () => {
    owner(); const fetch = vi.fn().mockImplementation(() => Promise.resolve(response({}))); vi.stubGlobal('fetch', fetch);
    await requestData('/anonymous-posts?limit=20', { headers: { authorization: 'Bearer attacker', 'Idempotency-Key': 'intent-1' } });
    await requestData('/opportunities', { headers: { Authorization: 'Bearer attacker' } });
    expect(fetch.mock.calls[0][0]).toBe(`${window.location.origin}/api/v1/anonymous-posts?limit=20`);
    expect(fetch.mock.calls[0][1]).toMatchObject({ headers: { Authorization: 'Bearer token.A', 'Idempotency-Key': 'intent-1' }, credentials: 'omit', cache: 'no-store', redirect: 'error', referrerPolicy: 'no-referrer' });
    expect(new Headers(fetch.mock.calls[1][1].headers).has('Authorization')).toBe(false);
  });
  it('permits only auth/me while the login token is not verified', async () => {
    owner(false); const fetch = vi.fn().mockImplementation(() => Promise.resolve(response({}))); vi.stubGlobal('fetch', fetch);
    await requestData('/auth/me'); await expect(requestData('/recruitments')).rejects.toMatchObject({ status: 401 }); expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('never sends a token over non-loopback HTTP', async () => {
    owner(); vi.stubEnv('VITE_API_BASE_URL', 'http://api.example.test/api/v1'); const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    await expect(requestData('/auth/me')).rejects.toMatchObject({ code: 'SECURE_TRANSPORT_REQUIRED' }); expect(fetch).not.toHaveBeenCalled();
  });
  it.each([200, 401, 403])('discards abort-ignoring old responses (%s) after account switch', async status => {
    const auth = owner(); let resolve!: (r: Response) => void; vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(done => { resolve = done; })));
    const pending = requestData('/anonymous-posts'); const assertion = expect(pending).rejects.toMatchObject({ code: 'CANCELLED' });
    auth.change(); resolve(response({ title: 'account-A-private' }, status)); await assertion; expect(auth.denied).not.toHaveBeenCalled();
  });
  it.each([401, 403])('notifies the current owner on %s without raw messages', async status => {
    const auth = owner(); vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(null, status)));
    await expect(requestData('/me/saved-opportunities')).rejects.not.toThrow('private-secret'); expect(auth.denied).toHaveBeenCalledExactlyOnceWith(1, status);
  });
  it('revokes captured old token without attaching the new account token', async () => {
    const auth = owner(); auth.change(); const fetch = vi.fn().mockResolvedValue(response({ status: 'ok' })); vi.stubGlobal('fetch', fetch);
    await requestSessionLogout('token.A'); expect(fetch.mock.calls[0][0]).toContain('/api/v1/auth/logout'); expect(fetch.mock.calls[0][1].headers).toEqual({ Authorization: 'Bearer token.A' });
  });
});
