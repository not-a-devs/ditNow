'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { E2EError } = require('../src/errors.cjs');
const { runP0BrowserE2E } = require('../src/runner.cjs');
const { buildStages } = require('../src/scenario.cjs');
const { FIXTURE_PASSWORD, FIXTURE_TOKEN, OPPORTUNITY_ID, baseEnv, createFakeApi } = require('./fixtures/fake-api.cjs');

// MockRunner: a fake browser whose contexts satisfy the runner's instrumentation calls. Stages are
// replaced by fixtures, so these tests exercise gating/redaction/cleanup, never product UI.
function mockBrowser() {
  const events = { contexts: 0, closed: 0, routes: 0, tracing: 0 };
  const page = { setDefaultTimeout() {}, on() {}, screenshot: async () => { throw new Error('no screenshots in tests'); }, locator: () => ({}) };
  const browser = {
    async newContext(options) {
      events.contexts += 1;
      events.options = options;
      return {
        tracing: { start: () => { events.tracing += 1; } },
        async route() { events.routes += 1; },
        async newPage() { return page; },
        async close() { events.closed += 1; },
      };
    },
    async close() { events.browserClosed = true; },
  };
  return { browser, events };
}

const forbidFetch = async () => assert.fail('network used without opt-in');
const forbidLaunch = async () => assert.fail('browser launched without opt-in');

test('default run without env is NOT_RUN: no browser, no network, exit 0', async () => {
  const { exitCode, report } = await runP0BrowserE2E({ env: {}, fetchImpl: forbidFetch, launchBrowser: forbidLaunch });
  const json = report.toJSON();
  assert.equal(exitCode, 0);
  assert.equal(json.status, 'NOT_RUN');
  assert.equal(json.reason, 'OPT_IN_MISSING');
  assert.deepEqual(json.stages, []);
  assert.equal(json.verified_claim, false);
});

test('opt-in with invalid config is NOT_RUN with exit 2 and names only', async () => {
  const env = baseEnv({ P0_E2E_WEB_URL: 'https://remote.example.com' });
  const { exitCode, report } = await runP0BrowserE2E({ env, fetchImpl: forbidFetch, launchBrowser: forbidLaunch });
  const text = JSON.stringify(report);
  assert.equal(exitCode, 2);
  assert.equal(report.toJSON().reason, 'CONFIG_INVALID');
  assert.ok(!text.includes('remote.example.com'));
  assert.ok(!text.includes(FIXTURE_PASSWORD));
});

test('non-DEMO accounts are refused before any browser work', async () => {
  const fake = createFakeApi({ recordSource: 'REAL' });
  const { exitCode, report } = await runP0BrowserE2E({ env: baseEnv(), fetchImpl: fake.fetchImpl, launchBrowser: forbidLaunch });
  const json = report.toJSON();
  assert.equal(exitCode, 1);
  assert.equal(json.stages[0].code, 'NOT_DEMO');
  assert.ok(json.stages.filter((s) => s.viewport !== null).every((s) => s.status === 'SKIPPED'));
  assert.ok(!fake.calls.some((c) => c.method === 'DELETE'));
});

test('pre-existing saved opportunity blocks opportunity stages without touching it', async () => {
  const fake = createFakeApi({ saved: [{ opportunity_id: OPPORTUNITY_ID, revision: 7, checks: [] }] });
  const { browser } = mockBrowser();
  const { report } = await runP0BrowserE2E({
    env: baseEnv(),
    fetchImpl: fake.fetchImpl,
    launchBrowser: async () => browser,
    stagesFactory: () => [{ id: 'opportunity.save_check_update_reload', deps: [], run: async () => assert.fail('must be skipped') }],
  });
  const json = report.toJSON();
  assert.equal(json.stages.find((s) => s.id === 'preflight.opportunity').code, 'PRECONDITION');
  assert.ok(json.stages.filter((s) => s.viewport).every((s) => s.status === 'SKIPPED'));
  assert.equal(fake.state.saved.length, 1);
});

test('launch failure messages are replaced by static codes', async () => {
  const fake = createFakeApi();
  const { exitCode, report } = await runP0BrowserE2E({
    env: baseEnv(),
    fetchImpl: fake.fetchImpl,
    launchBrowser: async () => {
      throw new Error(`launch failed with ${FIXTURE_PASSWORD}`);
    },
  });
  const json = report.toJSON();
  assert.equal(exitCode, 1);
  assert.deepEqual(
    json.stages.find((s) => s.id === 'browser.launch'),
    { id: 'browser.launch', viewport: null, status: 'FAIL', code: 'UNEXPECTED', detail: 'unhandled Error', duration_ms: json.stages[2].duration_ms },
  );
  assert.ok(!JSON.stringify(json).includes(FIXTURE_PASSWORD));
});

test('MockRunner: stage errors are redacted, resources cleaned, harness never reports PASS on failure', async () => {
  const fake = createFakeApi();
  const { browser, events } = mockBrowser();
  let seenMarker = null;
  const stagesFactory = () => [
    { id: 'auth.login_a', deps: [], run: async () => {} },
    {
      id: 'community.anonymous.create_edit_reload',
      deps: ['auth.login_a'],
      run: async (ctx) => {
        seenMarker = ctx.marker;
        const id = `post-${ctx.vp}`;
        fake.state.posts.set(id, { id, title: `${ctx.marker} 익명 ${ctx.vp}`, is_mine: true, revision: 1 });
        ctx.registry.register('anonymous_post', id, { revision: 1 });
        // A careless detail that embeds secrets must still come out masked.
        throw new E2EError('ASSERTION', `saw ${ctx.accounts.A.credential.password} ${ctx.accounts.A.token} ${id} ${ctx.accounts.A.identity.display_name}`);
      },
    },
    { id: 'community.anonymous.delete', deps: ['community.anonymous.create_edit_reload'], run: async () => assert.fail('must skip') },
  ];
  const { exitCode, report } = await runP0BrowserE2E({ env: baseEnv(), fetchImpl: fake.fetchImpl, launchBrowser: async () => browser, stagesFactory, mode: 'harness-self-test' });
  const json = report.toJSON();
  const text = JSON.stringify(json);
  assert.equal(exitCode, 1);
  assert.equal(json.status, 'FAIL');
  assert.equal(json.mode, 'harness-self-test');
  assert.match(seenMarker, /^E2EP0-/);
  for (const leaked of [FIXTURE_PASSWORD, FIXTURE_TOKEN, 'post-390', 'post-1280', '가상학생A', 'demoA0001', 'user-A-0001']) {
    assert.ok(!text.includes(leaked), `leaked ${leaked}`);
  }
  const failed = json.stages.filter((s) => s.id === 'community.anonymous.create_edit_reload');
  assert.equal(failed.length, 2);
  assert.ok(failed.every((s) => s.detail === 'saw *** *** *** ***'));
  assert.ok(json.stages.filter((s) => s.id === 'community.anonymous.delete').every((s) => s.status === 'SKIPPED'));
  assert.equal(json.cleanup.deleted, 2);
  assert.equal(fake.state.posts.size, 0);
  assert.equal(events.tracing, 0);
  assert.equal(events.closed, events.contexts);
  assert.equal(events.options.serviceWorkers, 'block');
  assert.equal(events.options.acceptDownloads, false);
  assert.ok(!('recordVideo' in events.options) && !('recordHar' in events.options));
  assert.equal(events.routes, events.contexts, 'every context installs the loopback-only route guard');
  assert.equal(fake.calls.filter((c) => c.path === '/auth/logout').length, 2);
});

test('real scenario keeps close-vs-delete as an opt-in separate sample and logs out last', () => {
  const ids = (opts) => buildStages(opts).map((s) => s.id);
  assert.ok(!ids({ includeClose: false }).includes('community.recruitment.close_not_deletable'));
  const withClose = ids({ includeClose: true });
  assert.ok(withClose.indexOf('community.recruitment.close_not_deletable') > withClose.indexOf('community.recruitment.delete'));
  assert.equal(withClose.at(-1), 'auth.logout_a');
  assert.equal(withClose[0], 'auth.login_a');
  assert.ok(withClose.indexOf('isolation.student_b') < withClose.indexOf('community.anonymous.delete'));
});
