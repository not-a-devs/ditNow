'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { reloadAndResume, apiPath } = require('../src/ui.cjs');
const { buildStages } = require('../src/scenario.cjs');

// A semantic page double for the current login/guard contract. No browser or network is used.
function currentPage(key = 'community') {
  const events = [], waiters = [], tokens = [], reloads = [];
  const web = 'http://127.0.0.1:5173', api = 'http://127.0.0.1:8000/api/v1';
  const identity = { user_id: '10000000-0000-4000-8000-000000000001', display_name: 'fixture display', record_source: 'DEMO' };
  let path = `/app/${key}`, signedIn = true, removed = false;
  const emit = (method, endpoint, data) => {
    const response = { request: () => ({ method: () => method }), url: () => api + endpoint, status: () => 200, json: async () => ({ data }) };
    for (const waiter of waiters.splice(0)) { if (waiter.predicate(response)) waiter.resolve(response); else waiters.push(waiter); }
  };
  const page = {
    url: () => web + path,
    reload: async () => { events.push('reload'); signedIn = false; },
    waitForURL: async predicate => assert.ok(predicate(new URL(web + path))),
    waitForResponse: predicate => new Promise(resolve => waiters.push({ predicate, resolve })),
    getByText: text => { const locator = { first: () => locator, waitFor: async () => {
      if (text === '로그인이 필요한 화면입니다') { assert.equal(signedIn, false); events.push('guard'); }
      else { assert.equal(text, identity.display_name); assert.equal(signedIn, true); }
    } }; return locator; },
    getByLabel: label => ({
      waitFor: async () => { assert.equal(path, '/app/login'); assert.equal(signedIn, false); },
      fill: async () => { assert.equal(path, '/app/login'); events.push(label); },
    }),
    getByRole: (role, options) => {
      if (role === 'tab') return { count: async () => 0 };
      if (role === 'navigation') return { getByRole: (childRole, childOptions) => {
        assert.equal(childRole, 'link'); assert.equal(childOptions.name, key === 'community' ? '익명 커뮤니티' : '팀원 모집');
        return { isVisible: async () => true, click: async () => { path = `/app/${key}`; events.push(`navigate ${key}`); emit('GET', key === 'community' ? '/anonymous-posts' : '/recruitments', { items: [] }); } };
      } };
      assert.equal(role, 'button');
      const button = { isVisible: async () => true, waitFor: async () => {}, first: () => button, click: async () => {
        if (options.name === '로그인 화면으로') { assert.equal(signedIn, false); path = '/app/login'; events.push('open login'); }
        else if (options.name === '가상 계정으로 로그인') {
          assert.equal(path, '/app/login'); signedIn = true; events.push('login');
          emit('POST', '/auth/login', { token: 'fixture.ui.token', token_type: 'Bearer', student_id: 'fixture-id', name: identity.display_name, record_source: 'DEMO' });
          emit('GET', '/auth/me', identity);
        } else if (options.name === '로그아웃') { signedIn = false; emit('POST', '/auth/logout', { status: 'ok' }); }
        else assert.fail('unexpected button');
      } };
      return button;
    },
    once: (event, callback) => { assert.equal(event, 'dialog'); page.acceptDialog = callback; },
    locator: selector => {
      const locator = {
        first: () => locator, locator: () => locator, filter: () => locator, count: async () => removed ? 0 : 1,
        waitFor: async () => { assert.equal(signedIn, true); assert.equal(selector, key === 'community' ? 'section[aria-labelledby="anon-heading"]' : 'section[aria-labelledby="recruit-heading"]'); },
        getByRole: (_, options) => ({ click: async () => {
          assert.equal(options.name, '모집글 취소 · 목록에서 제거');
          assert.ok(page.acceptDialog); await page.acceptDialog({ accept: async () => { events.push('confirm logical cancellation'); } });
          removed = true; emit('DELETE', '/recruitments/fixture-recruitment', { id: 'fixture-recruitment', deleted: true });
        } }),
      }; return locator;
    },
  };
  const ctx = { page, cfg: { webUrl: web }, apiBase: new URL(api), timeoutMs: 1000, trackToken: token => tokens.push(token), recordReload: outcome => reloads.push(outcome) };
  return { ctx, events, identity, tokens, reloads };
}

test('reload uses the real guard button and login route before re-reading the protected page', async () => {
  const { ctx, identity, events, tokens, reloads } = currentPage();
  await reloadAndResume(ctx, 'community', { studentId: 'fixture-id', password: 'fixture-password' }, identity);
  assert.deepEqual(events, ['reload', 'guard', 'open login', '가상 학번', '비밀번호', 'login', 'navigate community']);
  assert.deepEqual(tokens, ['fixture.ui.token']); assert.deepEqual(reloads, ['relogin_required']);
});

test('logout verifies the real signed-out guard then opens the explicit login form', async () => {
  const { ctx, events } = currentPage();
  await buildStages({ includeClose: false }).find(stage => stage.id === 'auth.logout_a').run(ctx);
  assert.deepEqual(events, ['guard', 'open login']);
});

test('API observers never confuse /api/v10 with /api/v1', () => {
  const ctx = { apiBase: new URL('http://127.0.0.1:8000/api/v1') };
  assert.equal(apiPath(ctx, 'http://127.0.0.1:8000/api/v10/auth/me'), null);
  assert.equal(apiPath(ctx, 'http://127.0.0.1:8000/api/v1/auth/me'), '/auth/me');
});

test('recruitment deletion drives the current logical-cancel label and confirmation dialog', async () => {
  const { ctx, identity, events } = currentPage('recruitments');
  ctx.accounts = { A: { token: 'fixture-preflight-token', credential: { studentId: 'fixture-id', password: 'fixture-password' }, identity } };
  ctx.state = { recruitment: { id: 'fixture-recruitment', title: 'fixture title', revision: 1 } };
  const marks = []; ctx.registry = { mark: (...args) => marks.push(args) };
  ctx.api = { expect: async (_, method, path) => { assert.equal(method, 'GET'); return path.startsWith('/recruitments?') ? { status: 200, data: { items: [] } } : { status: 404, data: null }; } };
  await buildStages({ includeClose: false }).find(stage => stage.id === 'community.recruitment.delete').run(ctx);
  assert.ok(events.includes('confirm logical cancellation'));
  assert.deepEqual(marks, [['recruitment', 'fixture-recruitment', 'deleted']]);
});
