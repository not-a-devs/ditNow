'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { createApiClient } = require('../src/api-client.cjs');
const { openInstrumentedPage } = require('../src/runner.cjs');
const { submitLogin } = require('../src/ui.cjs');

test('API login refuses a simulated 307 without sending credentials to its external destination', async () => {
  const destinations = [];
  const fetchImpl = async (url, init) => {
    destinations.push(new URL(url).origin);
    // Model native fetch redirect behaviour, without making any network request.
    if (init.redirect === 'error') throw new TypeError('redirection refused');
    destinations.push('https://outside.invalid');
    return new Response('{}');
  };
  const api = createApiClient({ apiUrl: 'http://127.0.0.1:8000/api/v1', fetchImpl, timeoutMs: 1000 });
  await assert.rejects(api.login({ studentId: 'synthetic', password: 'synthetic-password' }, 'fixture'), error => error.code === 'NETWORK' && !error.message.includes('password'));
  assert.deepEqual(destinations, ['http://127.0.0.1:8000']);
});

test('API rejects normalized and encoded path escapes before fetching or attaching a token', async () => {
  let calls = 0;
  const api = createApiClient({ apiUrl: 'http://127.0.0.1:8000/api/v1', fetchImpl: async () => { calls++; }, timeoutMs: 1000 });
  for (const path of ['/anonymous-posts/../health', '/x/./id', '/%2e%2e/auth', '/x%2fid', '/x%5cid', '/x\\id', '/auth/me#secret', '//outside.invalid']) {
    await assert.rejects(api.request('fixture', 'GET', path, { token: 'synthetic-token' }), error => error.code === 'ASSERTION');
  }
  assert.equal(calls, 0);
});

test('browser redirect interception fetches zero hops and never fulfills an external redirect', async () => {
  let handler, external = 0, fulfilled = 0, aborted = 0, disposed = 0;
  const page = { setDefaultTimeout() {}, on() {} };
  const context = { route: async (_, fn) => { handler = fn; }, newPage: async () => page };
  const cfg = { webUrl: 'http://127.0.0.1:5173', apiUrl: 'http://127.0.0.1:8000/api/v1', timeoutMs: 1000 };
  const obs = { blocked_external_requests: 0, blocked_redirects: 0, blocked_requests: 0 };
  await openInstrumentedPage({ newContext: async () => context }, cfg, { width: 390, height: 844 }, obs);
  await handler({
    request: () => ({ url: () => cfg.webUrl + '/app/login' }),
    fetch: async options => {
      if (options.maxRedirects !== 0) external++;
      assert.equal(options.maxRetries, 0);
      return { status: () => 307, dispose: async () => { disposed++; } };
    },
    fulfill: async () => { fulfilled++; }, abort: async () => { aborted++; },
  });
  assert.equal(external, 0); assert.equal(fulfilled, 0); assert.equal(aborted, 1); assert.equal(disposed, 1);
  assert.equal(obs.blocked_redirects, 1);
});

test('browser refuses a direct outside request without fetching and fulfills a nonredirect local response', async () => {
  let handler, fetched = 0, fulfilled = 0, aborted = 0;
  const cfg = { webUrl: 'http://127.0.0.1:5173', apiUrl: 'http://127.0.0.1:8000/api/v1', timeoutMs: 1000 };
  const obs = { blocked_external_requests: 0, blocked_redirects: 0, blocked_requests: 0 };
  await openInstrumentedPage({ newContext: async () => ({ route: async (_, fn) => { handler = fn; }, newPage: async () => ({ setDefaultTimeout() {}, on() {} }) }) }, cfg, { width: 390, height: 844 }, obs);
  const route = url => ({ request: () => ({ url: () => url }), fetch: async () => { fetched++; return { status: () => 200, dispose: async () => {} }; }, fulfill: async () => { fulfilled++; }, abort: async () => { aborted++; } });
  await handler(route('https://outside.invalid/login'));
  assert.equal(fetched, 0); assert.equal(aborted, 1);
  await handler(route(cfg.webUrl + '/app/login'));
  assert.equal(fetched, 1); assert.equal(fulfilled, 1); assert.equal(obs.blocked_external_requests, 1);
});

test('credential input is forbidden on an external or wrong local page', async () => {
  for (const url of ['https://outside.invalid/app/login', 'http://127.0.0.1:5173/app/community', 'http://127.0.0.1:5173/app/login?next=secret']) {
    let fills = 0;
    const page = { url: () => url, getByLabel: () => ({ fill: async () => { fills++; } }) };
    await assert.rejects(submitLogin({ page, cfg: { webUrl: 'http://127.0.0.1:5173' } }, { studentId: 'synthetic', password: 'synthetic-password' }, {}), error => error.code === 'PRECONDITION');
    assert.equal(fills, 0);
  }
});

test('navigation between student ID and password filling never sends the password to another origin', async () => {
  let url = 'http://127.0.0.1:5173/app/login', passwordFills = 0;
  const page = {
    url: () => url, waitForResponse: () => new Promise(() => {}),
    getByLabel: label => ({ fill: async () => { if (label === '가상 학번') url = 'https://outside.invalid/app/login'; else passwordFills++; } }),
  };
  await assert.rejects(submitLogin({ page, cfg: { webUrl: 'http://127.0.0.1:5173' }, timeoutMs: 1000, apiBase: new URL('http://127.0.0.1:8000/api/v1') }, { studentId: 'synthetic', password: 'synthetic-password' }, {}), error => error.code === 'PRECONDITION');
  assert.equal(passwordFills, 0);
});
