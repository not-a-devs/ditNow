#!/usr/bin/env node
'use strict';

// Usage: see docs/dev-prep/TASK_P0_BROWSER_E2E.md. Prints one redacted JSON report to stdout.
// Exit: 0 = PASS or NOT_RUN (no opt-in), 1 = FAIL, 2 = opt-in with invalid configuration.
const { runP0BrowserE2E } = require('./src/runner.cjs');

runP0BrowserE2E().then(
  ({ exitCode, report }) => {
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
    process.exitCode = exitCode;
  },
  () => {
    // Never print the raw error: it may embed request data. The runner itself catches stage errors.
    process.stdout.write(`${JSON.stringify({ schema: 'ditnow.p0-browser-e2e.report/v1', status: 'FAIL', reason: 'HARNESS_CRASH', verified_claim: false })}\n`);
    process.exitCode = 1;
  },
);
