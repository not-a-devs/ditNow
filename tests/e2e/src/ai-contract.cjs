'use strict';

const { E2EError } = require('./errors.cjs');
const GENERATOR = 'deterministic_rules_v1';
const MARKER = 'DITNOW_DEMO_P0_INTEGRATION';
const REASON_FIELDS = new Set(['target_scope.level', 'target_scope.department_codes', 'target_scope.academic_years', 'kind', 'title', 'organization', 'eligibility', 'deadline_at']);

function requireThat(value, label) {
  if (!value) throw new E2EError('ASSERTION', label);
}

function assertBasis(payload, identity) {
  const provenance = payload?.provenance;
  requireThat(provenance?.generator === GENERATOR && provenance.ai_generated === false
    && provenance.eligibility_guaranteed === false && typeof provenance.notice === 'string'
    && provenance.notice.trim(), 'reference generator and no-eligibility contract');
  const memberships = payload.context?.memberships;
  requireThat(Array.isArray(memberships) && memberships.length === 1
    && memberships[0].department_code === identity.department_code
    && memberships[0].grade === identity.academic_year, 'reference context differs from current own membership');
}

function assertReasons(reasons) {
  requireThat(Array.isArray(reasons) && reasons.length > 0 && reasons.length <= 30,
    'reference has no bounded evidence');
  requireThat(reasons.every(r => r && REASON_FIELDS.has(r.source_field)
    && typeof r.code === 'string'), 'reference evidence field is not in catalog contract');
}

function assertMatchPage(page, identity, opportunity) {
  assertBasis(page, identity);
  requireThat(Array.isArray(page.items) && page.items.length <= 20, 'reference list shape');
  const item = page.items.find(i => i?.opportunity?.id === opportunity.id);
  requireThat(item && item.opportunity.source_kind === 'DEMO'
    && item.opportunity.title === opportunity.title && opportunity.title.includes(MARKER),
  'approved DEMO opportunity missing from reference list');
  assertReasons(item.reasons);
  return item;
}

function assertBrief(brief, identity, opportunity) {
  assertBasis(brief, identity);
  requireThat(brief.opportunity?.id === opportunity.id && brief.opportunity.title === opportunity.title
    && brief.opportunity.source_kind === 'DEMO' && brief.match?.in_scope === true,
  'brief differs from approved DEMO reference');
  assertReasons(brief.match.reasons);
  requireThat(Array.isArray(brief.cautions)
    && brief.cautions.some(c => c.code === 'NOT_ELIGIBILITY_DECISION')
    && brief.cautions.some(c => c.code === 'DEMO_SOURCE')
    && brief.cautions.some(c => c.code === 'UNVERIFIED_SOURCE'), 'DEMO unknown-source cautions missing');
  requireThat(Array.isArray(brief.procedure) && brief.procedure.length <= 10
    && brief.procedure.every(s => typeof s.evidence_field === 'string' && typeof s.available === 'boolean'),
  'brief procedure must contain explicit original-field evidence');
}

function ownSaved(data, opportunityId) {
  requireThat(data && Array.isArray(data.items), 'own saved list shape');
  return data.items.find(s => s?.opportunity_id === opportunityId) ?? null;
}

function assertNoSavedChange(before, after) {
  requireThat(JSON.stringify(before) === JSON.stringify(after), 'draft preview or cancellation changed server records');
}

function assertSavedDraft(row, { opportunityId, memo, checkText }) {
  requireThat(row?.opportunity_id === opportunityId && row.memo === memo
    && Array.isArray(row.checks), 'saved draft differs from explicit selection');
  const matches = row.checks.filter(c => c?.text === checkText);
  requireThat(matches.length === 1 && matches[0].id && Number.isSafeInteger(matches[0].revision)
    && matches[0].revision >= 1, 'explicit checklist selection missing or duplicated');
  requireThat(row.checks.length === 1, 'unselected checklist items were written');
  return matches[0];
}

module.exports = { assertBasis, assertMatchPage, assertBrief, ownSaved,
  assertNoSavedChange, assertSavedDraft, requireThat };
