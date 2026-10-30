#!/usr/bin/env node
'use strict';

// TASK-AI-OPP-01C. Both P0_E2E_AI_RUN=1 and the existing P0 opt-in/config are required.
// This does not provision data or enable a model. Root owns live execution and credentials.
const { runAiOpportunityE2E } = require('./src/ai-runner.cjs');

runAiOpportunityE2E().then(
  ({ exitCode, report }) => { process.stdout.write(`${JSON.stringify(report, null, 2)}\n`); process.exitCode = exitCode; },
  () => { process.stdout.write(`${JSON.stringify({ schema: 'ditnow.ai-opportunity-e2e.report/v1', status: 'FAIL', reason: 'HARNESS_CRASH', verified_claim: false })}\n`); process.exitCode = 1; },
);
