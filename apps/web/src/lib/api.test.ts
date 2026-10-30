import { describe, expect, it, vi } from 'vitest';
import { ApiError, registerAuthentication, requestData, resolveApiUrl } from './api';

describe('demo namespace authentication allowlist', () => {
  async function headersFor(path: string, init: RequestInit = {}) {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ data: {} }), { status: 200, headers: { 'content-type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    const unregister = registerAuthentication({ read: () => ({ generation: 7, token: 'verified-token', verified: true }), denied: () => undefined });
    try { await requestData(path, init).catch(() => undefined); } finally { unregister(); vi.unstubAllGlobals(); }
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const call = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    return { headers: new Headers(call[1].headers), init: call[1] };
  }

  it.each(['/me/demo-services', '/me/demo-attendance/sessions', '/me/demo-profile', '/me/demo-action-center/items?x=1', '/me/demo-channels/'])('injects the verified bearer with no-store for %s', async path => {
    const { headers, init } = await headersFor(path);
    expect(headers.get('Authorization')).toBe('Bearer verified-token');
    expect(init.cache).toBe('no-store');
    expect(init.credentials).toBe('omit');
  });

  it.each(['/me/demo-services-evil', '/me/demo-attendanceX', '/me/demo-profile-evil', '/me/demo-action-centerX', '/me/demo-channels-evil', '/me/demo', '/me/other', '/me', '/demo-services', '/campus-travel/calculate', '/data-provenance'])('never sends the bearer to near-miss or public path %s', async path => {
    const { headers } = await headersFor(path, path.startsWith('/campus-travel') ? { method: 'POST', body: '{}' } : {});
    expect(headers.get('Authorization')).toBeNull();
  });

  it('rejects demo namespaces before network when the identity is not yet verified', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const unregister = registerAuthentication({ read: () => ({ generation: 1, token: 'pending', verified: false }), denied: () => undefined });
    try { await expect(requestData('/me/demo-attendance')).rejects.toMatchObject({ status: 401 }); } finally { unregister(); vi.unstubAllGlobals(); }
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('public API transport', () => {
  it('keeps relative API paths inside the configured base', () => {
    expect(resolveApiUrl('/health', 'https://api.example.test/api/v1')).toBe('https://api.example.test/api/v1/health');
    expect(resolveApiUrl('/health', '')).toBe(`${window.location.origin}/api/v1/health`);
    expect(resolveApiUrl('/health', '/api/v1')).toBe(`${window.location.origin}/api/v1/health`);
  });
  it.each(['javascript:alert(1)', 'https://user:secret@api.example.test', '/remote', 'https://api.example.test?token=secret'])('rejects invalid base without echoing it: %s', base => {
    try { resolveApiUrl('/health', base); throw new Error('should fail'); } catch (error) { expect(error).toBeInstanceOf(ApiError); expect((error as Error).message).not.toContain('secret'); }
  });
  it.each(['//evil.test/path', '/../session', 'https://evil.test', '/%2e%2e/session', '/%2e%2e%2fsession', '/%2E%2E%5Csession', '/path%2Fother', '/path#token'])('rejects paths escaping the base: %s', path => {
    expect(() => resolveApiUrl(path, 'https://api.example.test/api/v1')).toThrow(ApiError);
  });
  it('unwraps data and uses same-origin credentials by default', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { status: 'ok' } }), { status: 200 }));
    vi.stubGlobal('fetch', fetch);
    expect(await requestData('/health')).toEqual({ status: 'ok' });
    expect(fetch.mock.calls[0][1].credentials).toBe('same-origin');
  });
  it('returns safe structured errors without server messages', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 'FORBIDDEN', message: 'private-password-secret', request_id: '12345678-1234-1234-1234-123456789012' }), { status: 403 })));
    await expect(requestData('/health')).rejects.toMatchObject({ code: 'FORBIDDEN', status: 403, requestId: '12345678-1234-1234-1234-123456789012' });
    await expect(requestData('/health')).rejects.not.toThrow('private-password-secret');
  });
  it('rejects a successful response without the contract wrapper', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 200 })));
    await expect(requestData('/health')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  });
  it('redacts network exception details', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('secret-url-token')));
    await expect(requestData('/health')).rejects.toMatchObject({ code: 'NETWORK', status: 0 });
    await expect(requestData('/health')).rejects.not.toThrow('secret-url-token');
  });
});
