'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { E2EError, toSafeFailure } = require('../src/errors.cjs');
const { Redactor } = require('../src/redact.cjs');
const { Report } = require('../src/report.cjs');

test('redactor masks registered secrets, URL-encoded forms, bearer tokens, JWTs and UUIDs', () => {
  const r = new Redactor();
  r.add('pa ss/word');
  r.add('ab'); // too short to mask safely; ignored
  const out = r.mask(
    'pw=pa ss/word enc=pa%20ss%2Fword Authorization: Bearer abc.def-ghi== jwt=eyJhbGci.eyJzdWIi.sig id=0b9c1f3e-6a51-4c2e-9d0a-111122223333 ab',
  );
  assert.ok(!out.includes('pa ss/word'));
  assert.ok(!out.includes('pa%20ss%2Fword'));
  assert.ok(!out.includes('abc.def-ghi'));
  assert.ok(!out.includes('eyJhbGci'));
  assert.ok(out.includes('<uuid>'));
  assert.ok(out.endsWith(' ab'));
  assert.ok(r.mask('x'.repeat(1000)).length <= 301);
});

test('failures expose only static codes and harness-written details', () => {
  const r = new Redactor();
  r.add('SECRET-PW-123');
  const raw = new Error('locator.fill("SECRET-PW-123") failed; body={"token":"t"}');
  assert.deepEqual(toSafeFailure(raw, r), { code: 'UNEXPECTED', detail: 'unhandled Error' });
  const timeout = Object.assign(new Error('waiting for SECRET-PW-123'), { name: 'TimeoutError' });
  assert.deepEqual(toSafeFailure(timeout, r), { code: 'TIMEOUT', detail: 'step timed out' });
  const weird = Object.assign(new Error('x'), { name: 'SECRET-PW-123' });
  assert.equal(toSafeFailure(weird, r).detail, 'unhandled Error');
  const own = new E2EError('HTTP_STATUS', 'login SECRET-PW-123: expected 200 got 401');
  assert.deepEqual(toSafeFailure(own, r), { code: 'HTTP_STATUS', detail: 'login ***: expected 200 got 401' });
  assert.equal(new E2EError('MADE_UP', 'x').code, 'UNEXPECTED');
  assert.equal(toSafeFailure('string thrown', r).code, 'UNEXPECTED');
});

test('report never claims VERIFIED and requires every stage to PASS', () => {
  const r = new Redactor();
  const report = new Report({ redactor: r });
  assert.equal(report.status, 'NOT_RUN');
  report.addStage({ id: 'a', status: 'PASS' });
  assert.equal(report.status, 'INCOMPLETE');
  report.setCleanup({ failed: 0 });
  assert.equal(report.status, 'PASS');
  report.addStage({ id: 'b', viewport: 390, status: 'SKIPPED', code: 'DEPENDENCY_FAILED' });
  assert.equal(report.status, 'FAIL');
  const json = report.toJSON();
  assert.equal(json.verified_claim, false);
  assert.match(json.note, /not VERIFIED/);

  const notRun = new Report({ redactor: r });
  notRun.setReason('OPT_IN_MISSING');
  assert.equal(notRun.toJSON().status, 'NOT_RUN');

  const cleanupFail = new Report({ redactor: r });
  cleanupFail.addStage({ id: 'a', status: 'PASS' });
  cleanupFail.setCleanup({ failed: 1 });
  assert.equal(cleanupFail.status, 'FAIL');
});

test('cleanup residue, skipped markers and budget limits cannot report PASS', () => {
  for (const failure of [{ residual_closed: 1 }, { skipped_not_owned_marker: 1 }, { budget_exhausted: true }]) {
    const report = new Report({ redactor: new Redactor() }); report.addStage({ id: 'ui', status: 'PASS' }); report.setCleanup({ failed: 0, ...failure });
    assert.equal(report.status, 'INCOMPLETE'); assert.equal(report.toJSON().verified_claim, false);
  }
});

test('page errors and missing private cache protection prevent an overall PASS', () => {
  for (const key of ['page_errors', 'private_responses_without_no_store', 'blocked_redirects', 'blocked_requests', 'blocked_external_requests']) {
    const report = new Report({ redactor: new Redactor() }); report.addStage({ id: 'ui', status: 'PASS' }); report.setCleanup({ failed: 0 }); report.observe(390, key, 1);
    assert.equal(report.status, 'FAIL');
  }
});
