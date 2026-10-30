'use strict';

// Offline harness-only tests. Fake fetch/page objects are never product or real-DB evidence.
const test = require('node:test');
const assert = require('node:assert/strict');
const { runAiOpportunityE2E } = require('../src/ai-runner.cjs');
const { assertBasis, assertMatchPage, assertBrief, ownSaved, assertNoSavedChange, assertSavedDraft } = require('../src/ai-contract.cjs');
const { AI, buildAiStages, watchMutations, navigateAi } = require('../src/ai-scenario.cjs');
const { buildStages } = require('../src/scenario.cjs');
const { E2EError } = require('../src/errors.cjs');
const { baseEnv, createFakeApi, OPPORTUNITY_ID, FIXTURE_PASSWORD } = require('./fixtures/fake-api.cjs');

const identity = { department_code: 'DEMO-A', academic_year: 1 };
const opportunity = { id: OPPORTUNITY_ID, title: '[가상] 통합검증용 기회 DITNOW_DEMO_P0_INTEGRATION' };
const basis = () => ({ provenance: { generator: 'deterministic_rules_v1', ai_generated: false, eligibility_guaranteed: false, notice: '학교 자격 판정 아님' }, context: { memberships: [{ department_code: 'DEMO-A', grade: 1 }] } });
const reasons = () => [{ code: 'SCHOOL_WIDE', source_field: 'target_scope.level' }];
const detail = () => ({ ...basis(), opportunity: { ...opportunity, source_kind: 'DEMO' }, match: { in_scope: true, reasons: reasons() }, cautions: ['NOT_ELIGIBILITY_DECISION', 'DEMO_SOURCE', 'UNVERIFIED_SOURCE'].map(code => ({ code })), procedure: [{ evidence_field: 'original_url', available: false }] });
const forbidden = async () => assert.fail('must not use browser/network');

function fakeBrowser() {
  const events = { closed: 0 };
  const page = { setDefaultTimeout() {}, on() {} };
  const browser = {
    newContext: async () => ({ route: async () => {}, newPage: async () => page, close: async () => { events.closed += 1; } }),
    close: async () => { events.browserClosed = true; },
  };
  return { browser, events };
}

test('AI default gate reads only its opt-in and launches/fetches nothing', async () => {
  const env = new Proxy({}, { get: (_, key) => { assert.equal(key, 'P0_E2E_AI_RUN'); return undefined; } });
  const { exitCode, report } = await runAiOpportunityE2E({ env, fetchImpl: forbidden, launchBrowser: forbidden });
  const json = report.toJSON();
  assert.equal(exitCode, 0); assert.equal(json.status, 'NOT_RUN');
  assert.equal(json.reason, 'AI_OPT_IN_MISSING'); assert.equal(json.verified_claim, false);
  assert.equal(json.schema, 'ditnow.ai-opportunity-e2e.report/v1'); assert.deepEqual(json.stages, []);
});

test('AI opt-in alone does not silently enable existing P0 opt-in', async () => {
  const { report } = await runAiOpportunityE2E({ env: { P0_E2E_AI_RUN: '1' }, fetchImpl: forbidden, launchBrowser: forbidden });
  assert.equal(report.toJSON().status, 'NOT_RUN');
  assert.equal(report.toJSON().reason, 'OPT_IN_MISSING');
});

test('AI configured remote URL is refused and credentials stay out of output', async () => {
  const { exitCode, report } = await runAiOpportunityE2E({ env: baseEnv({ P0_E2E_AI_RUN: '1', P0_E2E_WEB_URL: 'https://external.invalid' }), fetchImpl: forbidden, launchBrowser: forbidden });
  const json = JSON.stringify(report);
  assert.equal(exitCode, 2); assert.ok(!json.includes(FIXTURE_PASSWORD)); assert.ok(!json.includes('external.invalid'));
});

test('AI stages require preview/cancel before explicit save and use unchanged P0 cleanup/logout', () => {
  const stages = buildAiStages();
  const ids = stages.map(s => s.id);
  assert.deepEqual(ids, ['auth.login_a', 'opportunity.ai_reference_preview_cancel', 'opportunity.ai_explicit_save', 'opportunity.ai_fresh_session_read', 'isolation.ai_student_b', 'opportunity.remove', 'auth.logout_a']);
  assert.deepEqual(stages[2].deps, ['opportunity.ai_reference_preview_cancel']);
  assert.deepEqual(stages[4].deps, ['opportunity.ai_fresh_session_read']);
  const old = buildStages({ includeClose: false });
  assert.equal(stages.at(-2).run, old.find(s => s.id === 'opportunity.remove').run);
  assert.equal(stages.at(-1).run, old.find(s => s.id === 'auth.logout_a').run);
  assert.equal(old.length, 9); // Existing P0 scenario is preserved.
});

function navigationPage({ mobile = false, href = '/app/ai' } = {}) {
  const events = { clicks: 0, toggles: 0, inputWaits: 0 };
  let current = 'http://127.0.0.1:5753/app/community';
  const page = {
    url: () => current,
    getByRole: role => {
      assert.equal(role, 'navigation');
      return { getByRole: (childRole, options) => {
        assert.equal(childRole, 'link');
        // The real navigation link includes its visible AI badge in its accessible name.
        const accessibleName = `${AI.navigation} AI`;
        assert.equal(options.exact ? accessibleName === options.name : accessibleName.includes(options.name), true);
        return {
          isVisible: async () => !mobile || events.toggles > 0,
          getAttribute: async name => { assert.equal(name, 'href'); return href; },
          click: async () => { events.clicks += 1; current = new URL(href, current).href; },
        };
      } };
    },
    locator: () => ({ first: () => ({ click: async () => { events.toggles += 1; } }) }),
    waitForURL: async predicate => { assert.equal(predicate(new URL(current)), true); },
    getByLabel: label => {
      assert.equal(label, AI.keyword);
      return { waitFor: async () => { events.inputWaits += 1; } };
    },
  };
  return { page, events };
}

for (const mobile of [false, true]) {
  test(`AI badge accessible name navigates to the exact approved route (${mobile ? 'mobile' : 'desktop'})`, async () => {
    const { page, events } = navigationPage({ mobile });
    await navigateAi({ page, timeoutMs: 100 });
    assert.equal(new URL(page.url()).pathname, '/app/ai');
    assert.deepEqual(events, { clicks: 1, toggles: Number(mobile), inputWaits: 1 });
  });
}

test('AI navigation refuses unrelated or external hrefs before clicking', async () => {
  for (const href of ['/app/ai-other', '/app/ai?next=other', '/app/ai#other', 'https://external.invalid/app/ai', null]) {
    const { page, events } = navigationPage({ href });
    await assert.rejects(navigateAi({ page, timeoutMs: 100 }), error => error instanceof E2EError && error.code === 'ASSERTION');
    assert.equal(events.clicks, 0);
    assert.equal(events.inputWaits, 0);
  }
});

test('reference context must match current own department and year, not another student', () => {
  assert.doesNotThrow(() => assertBasis(basis(), identity));
  assert.throws(() => assertBasis(basis(), { ...identity, department_code: 'DEMO-B' }), E2EError);
  assert.throws(() => assertBasis(basis(), { ...identity, academic_year: 2 }), E2EError);
  assert.throws(() => assertBasis({ ...basis(), context: { memberships: [] } }, identity), E2EError);
});

test('generated AI or eligibility claims cannot be passed as the approved rule-based mode', () => {
  for (const field of ['ai_generated', 'eligibility_guaranteed']) {
    const data = basis(); data.provenance[field] = true;
    assert.throws(() => assertBasis(data, identity), E2EError);
  }
  const data = basis(); data.provenance.generator = 'invented';
  assert.throws(() => assertBasis(data, identity), E2EError);
});

test('match list requires exactly the approved DEMO ID/title and original-field evidence', () => {
  const page = { ...basis(), items: [{ opportunity: { ...opportunity, source_kind: 'DEMO' }, reasons: reasons() }] };
  assert.equal(assertMatchPage(page, identity, opportunity).opportunity.id, OPPORTUNITY_ID);
  assert.throws(() => assertMatchPage(page, identity, { ...opportunity, id: 'another-id' }), E2EError);
  page.items[0].reasons[0].source_field = 'student_password';
  assert.throws(() => assertMatchPage(page, identity, opportunity), E2EError);
});

test('brief must preserve unknown/DEMO/no-eligibility warnings; hallucinated ID fails', () => {
  assert.doesNotThrow(() => assertBrief(detail(), identity, opportunity));
  const missingWarning = detail(); missingWarning.cautions.pop();
  assert.throws(() => assertBrief(missingWarning, identity, opportunity), E2EError);
  const other = detail(); other.opportunity.id = 'another-id';
  assert.throws(() => assertBrief(other, identity, opportunity), E2EError);
});

test('preview cancellation rejects any persisted memo/check or new saved row', () => {
  const empty = { items: [] };
  assert.doesNotThrow(() => assertNoSavedChange(empty, { items: [] }));
  assert.throws(() => assertNoSavedChange(empty, { items: [{ opportunity_id: OPPORTUNITY_ID, memo: 'changed' }] }), E2EError);
  assert.equal(ownSaved(empty, OPPORTUNITY_ID), null);
  assert.throws(() => ownSaved({ items: {} }, OPPORTUNITY_ID), E2EError);
});

test('saved requery rejects duplicate/unselected items and stale memo', () => {
  const options = { opportunityId: OPPORTUNITY_ID, memo: 'run marker', checkText: 'run choice' };
  const row = { opportunity_id: OPPORTUNITY_ID, memo: options.memo, checks: [{ id: 'opaque-check-id', text: options.checkText, revision: 1 }] };
  assert.equal(assertSavedDraft(row, options).id, 'opaque-check-id');
  assert.throws(() => assertSavedDraft({ ...row, checks: [...row.checks, ...row.checks] }, options), E2EError);
  assert.throws(() => assertSavedDraft({ ...row, memo: 'old memo' }, options), E2EError);
  assert.throws(() => assertSavedDraft({ ...row, checks: [...row.checks, { id: 'unselected', text: 'other', revision: 1 }] }, options), E2EError);
});

test('preview mutation observer sees unknown API writes too and removes only its listener', () => {
  const listeners = new Set();
  const page = { on: (type, cb) => { assert.equal(type, 'request'); listeners.add(cb); }, off: (type, cb) => { assert.equal(type, 'request'); listeners.delete(cb); } };
  const observer = watchMutations({ page, apiBase: new URL('http://127.0.0.1:8000/api/v1') });
  const emit = (method, path) => listeners.forEach(fn => fn({ method: () => method, url: () => `http://127.0.0.1:8000${path}` }));
  emit('GET', '/api/v1/me/opportunity-matches'); emit('POST', '/api/v10/not-this-api');
  assert.equal(observer.count(), 0);
  emit('PUT', `/api/v1/me/saved-opportunities/${OPPORTUNITY_ID}`); emit('POST', '/api/v1/unexpected-write');
  assert.equal(observer.count(), 2); observer.stop(); assert.equal(listeners.size, 0);
});

test('MockRunner partial failure cleans registered marker resources and every token; never real-DB PASS', async () => {
  const fake = createFakeApi(); const { browser, events } = fakeBrowser();
  const result = await runAiOpportunityE2E({ env: baseEnv({ P0_E2E_AI_RUN: '1' }), fetchImpl: fake.fetchImpl, launchBrowser: async () => browser, mode: 'harness-self-test',
    stagesFactory: () => [{ id: 'opportunity.partial', deps: [], run: async ctx => {
      ctx.registry.register('saved_opportunity', OPPORTUNITY_ID);
      fake.state.saved = [{ opportunity_id: OPPORTUNITY_ID, memo: ctx.marker, revision: 1, checks: [] }];
      throw new E2EError('ASSERTION', `fixture only ${FIXTURE_PASSWORD}`);
    } }] });
  const report = result.report.toJSON();
  assert.equal(result.exitCode, 1); assert.equal(report.status, 'FAIL');
  assert.equal(report.mode, 'harness-self-test'); assert.equal(report.verified_claim, false);
  assert.equal(report.model_generation, 'NOT_TESTED'); assert.ok(!JSON.stringify(report).includes(FIXTURE_PASSWORD));
  assert.equal(fake.state.saved.length, 0); assert.equal(report.cleanup.sessions_failed, 0);
  assert.equal(events.closed, 2); assert.equal(events.browserClosed, true);
});

test('MockRunner cleanup conflict remains FAIL rather than silently reporting success', async () => {
  const fake = createFakeApi({ failDeletes: true }); const { browser } = fakeBrowser();
  const result = await runAiOpportunityE2E({ env: baseEnv({ P0_E2E_AI_RUN: '1' }), fetchImpl: fake.fetchImpl, launchBrowser: async () => browser, mode: 'harness-self-test',
    stagesFactory: () => [{ id: 'opportunity.partial', deps: [], run: async ctx => {
      fake.state.saved = [{ opportunity_id: OPPORTUNITY_ID, memo: ctx.marker, revision: 1, checks: [] }];
      ctx.registry.register('saved_opportunity', OPPORTUNITY_ID);
    } }] });
  assert.equal(result.exitCode, 1); assert.equal(result.report.status, 'FAIL');
  assert.ok(result.report.toJSON().cleanup.failed > 0); assert.equal(fake.state.saved.length, 1);
});
