'use strict';

const { Report } = require('./report.cjs');
const { Redactor } = require('./redact.cjs');
const { runP0BrowserE2E } = require('./runner.cjs');
const { buildAiStages } = require('./ai-scenario.cjs');

function aiReport(report) {
  return {
    get status() { return report.status; },
    toJSON() {
      return { ...report.toJSON(), schema: 'ditnow.ai-opportunity-e2e.report/v1',
        scope: 'approved-demo-opportunity-reference-and-explicit-save',
        expected_generator: 'deterministic_rules_v1',
        model_generation: 'NOT_TESTED', verified_claim: false };
    },
  };
}

async function runAiOpportunityE2E(options = {}) {
  const env = options.env ?? process.env;
  // Read this single opt-in first. Do not inspect passwords/config or load a browser otherwise.
  if (env.P0_E2E_AI_RUN !== '1') {
    const report = new Report({ redactor: new Redactor(), mode: options.mode ?? 'live' });
    report.setReason('AI_OPT_IN_MISSING');
    return { exitCode: 0, report: aiReport(report) };
  }
  const result = await runP0BrowserE2E({ ...options, env,
    stagesFactory: options.stagesFactory ?? buildAiStages });
  return { ...result, report: aiReport(result.report) };
}

module.exports = { runAiOpportunityE2E };
