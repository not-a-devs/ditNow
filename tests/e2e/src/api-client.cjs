'use strict';

const { randomUUID } = require('node:crypto');
const { E2EError } = require('./errors.cjs');

/**
 * Minimal client for the harness's own requery/cleanup through the real API. Bodies stay in
 * memory; errors carry only the caller's static label, never URLs with IDs or response text.
 */
function createApiClient({ apiUrl, fetchImpl, timeoutMs }) {
  const base = new URL(`${apiUrl}/`);

  async function request(label, method, path, { token, body, headers = {} } = {}) {
    if (!path.startsWith('/') || path.startsWith('//')) throw new E2EError('ASSERTION', `${label}: bad path`);
    const url = new URL(path.slice(1), base);
    if (url.origin !== base.origin) throw new E2EError('ASSERTION', `${label}: origin changed`);
    const init = { method, headers: { Accept: 'application/json', ...headers }, signal: AbortSignal.timeout(timeoutMs) };
    if (token) init.headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(body);
    }
    let response;
    try {
      response = await fetchImpl(url, init);
    } catch {
      throw new E2EError('NETWORK', `${label}: request failed`);
    }
    let envelope = null;
    try {
      envelope = await response.json();
    } catch {
      envelope = null;
    }
    return {
      status: response.status,
      data: envelope && typeof envelope === 'object' ? envelope.data ?? null : null,
      cacheControl: response.headers?.get?.('cache-control') ?? null,
    };
  }

  async function expect(label, method, path, statuses, options) {
    const result = await request(label, method, path, options);
    const allowed = [].concat(statuses);
    if (!allowed.includes(result.status)) {
      throw new E2EError('HTTP_STATUS', `${label}: expected ${allowed.join('|')} got ${result.status}`);
    }
    return result;
  }

  return {
    request,
    expect,
    idempotencyKey: () => `e2e-${randomUUID()}`,
    async login(credential, label) {
      const { data } = await expect(`${label} login`, 'POST', '/auth/login', 200, {
        body: { student_id: credential.studentId, password: credential.password },
      });
      if (!data || typeof data.token !== 'string' || data.token_type !== 'Bearer') {
        throw new E2EError('ASSERTION', `${label} login: LoginData shape mismatch`);
      }
      if (data.record_source !== 'DEMO') throw new E2EError('NOT_DEMO', `${label} login: record_source is not DEMO`);
      return data;
    },
    async me(token, label) {
      const { data } = await expect(`${label} /auth/me`, 'GET', '/auth/me', 200, { token });
      if (!data || typeof data.user_id !== 'string' || typeof data.display_name !== 'string') {
        throw new E2EError('ASSERTION', `${label} /auth/me: shape mismatch`);
      }
      if (data.record_source !== 'DEMO') throw new E2EError('NOT_DEMO', `${label} /auth/me: record_source is not DEMO`);
      return data;
    },
    async logout(token) {
      try {
        await request('logout', 'POST', '/auth/logout', { token });
      } catch {
        // Best effort: token expiry still bounds an unrevoked harness session.
      }
    },
  };
}

module.exports = { createApiClient };
