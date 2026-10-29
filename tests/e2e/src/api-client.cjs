'use strict';

const { randomUUID } = require('node:crypto');
const { E2EError } = require('./errors.cjs');

/**
 * Minimal client for the harness's own requery/cleanup through the real API. Bodies stay in
 * memory; errors carry only the caller's static label, never URLs with IDs or response text.
 */
function createApiClient({ apiUrl, fetchImpl, timeoutMs, onToken = () => {} }) {
  const base = new URL(`${apiUrl}/`);

  async function request(label, method, path, { token, body, headers = {} } = {}) {
    if (!path.startsWith('/') || path.startsWith('//') || path.includes('\\')
      || /(?:^|\/)\.{1,2}(?:\/|$)/.test(path.split('?')[0])
      || /%(?:2e|2f|5c)/i.test(path.split('?')[0])) throw new E2EError('ASSERTION', `${label}: bad path`);
    const url = new URL(path.slice(1), base);
    if (url.origin !== base.origin || !url.pathname.startsWith(base.pathname) || url.hash) throw new E2EError('ASSERTION', `${label}: target changed`);
    const init = { method, headers: { Accept: 'application/json', ...headers }, redirect: 'error',
      credentials: 'omit', cache: 'no-store', referrerPolicy: 'no-referrer', signal: AbortSignal.timeout(timeoutMs) };
    if (token) init.headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(body);
    }
    let response;
    try {
      response = await fetchImpl(url, init);
      if (response.redirected || (response.status >= 300 && response.status < 400)) throw new Error('redirect refused');
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
      if (!data || typeof data.token !== 'string' || !/^[A-Za-z0-9._~+/-]{8,512}={0,2}$/.test(data.token) || data.token_type !== 'Bearer') {
        throw new E2EError('ASSERTION', `${label} login: LoginData shape mismatch`);
      }
      onToken(data.token); // Also revoke known tokens if a later provenance check fails.
      if (data.student_id !== credential.studentId || typeof data.name !== 'string' || !data.name.trim()
        || Object.keys(data).some(key => !['token', 'token_type', 'student_id', 'name', 'record_source'].includes(key))) {
        throw new E2EError('ASSERTION', `${label} login: LoginData shape mismatch`);
      }
      if (data.record_source !== 'DEMO') throw new E2EError('NOT_DEMO', `${label} login: record_source is not DEMO`);
      return data;
    },
    async me(token, label) {
      const { data } = await expect(`${label} /auth/me`, 'GET', '/auth/me', 200, { token });
      const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value);
      if (!data || !uuid(data.user_id) || !uuid(data.department_id)
        || typeof data.display_name !== 'string' || !data.display_name.trim()
        || typeof data.department_code !== 'string' || !data.department_code.trim()
        || !Number.isSafeInteger(data.academic_year) || data.academic_year < 1 || data.community_access !== true
        || Object.keys(data).some(key => !['user_id', 'display_name', 'record_source', 'department_id', 'department_code', 'academic_year', 'community_access'].includes(key))) {
        throw new E2EError('ASSERTION', `${label} /auth/me: shape mismatch`);
      }
      if (data.record_source !== 'DEMO') throw new E2EError('NOT_DEMO', `${label} /auth/me: record_source is not DEMO`);
      return data;
    },
    async logout(token) {
      try {
        const result = await request('logout', 'POST', '/auth/logout', { token });
        if (result.status !== 200 || result.data?.status !== 'ok') return false;
        const after = await request('verify logout', 'GET', '/auth/me', { token });
        return after.status === 401;
      } catch {
        return false; // Caller reports incomplete cleanup; expiry is not a verified revocation.
      }
    },
  };
}

module.exports = { createApiClient };
