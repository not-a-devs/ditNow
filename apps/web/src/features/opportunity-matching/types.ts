// FR-OPP-002 matching DTOs mirrored from services/api/app/features/opportunity_matching/models.py.
// Opportunity fields reuse the API-OPP types. Replace with generated OpenAPI types once root
// mounts the router and exports the snapshot.
import type { OpportunityDetail, OpportunityKind, OpportunitySummary } from '../opportunities/types';

export type ReasonCode =
  | 'SCHOOL_WIDE'
  | 'DEPARTMENT_MATCH'
  | 'GRADE_MATCH'
  | 'KIND_INTEREST'
  | 'KEYWORD_INTEREST'
  | 'DEADLINE_SOON';
export type Window = 'UPCOMING' | 'OPEN' | 'CLOSED' | 'NO_DEADLINE';
export type Freshness = 'CURRENT' | 'STALE' | 'UNVERIFIED';
export type CautionCode =
  | 'NOT_ELIGIBILITY_DECISION'
  | 'EXTERNAL_SUBMISSION'
  | 'DEMO_SOURCE'
  | 'NEEDS_VERIFICATION'
  | 'STALE_SOURCE'
  | 'UNVERIFIED_SOURCE'
  | 'DEADLINE_PASSED'
  | 'NOT_YET_OPEN'
  | 'OUT_OF_SCOPE'
  | 'NO_APPLICATION_PROCEDURE';
export type StepCode =
  | 'CHECK_ORIGINAL'
  | 'DOWNLOAD_FORM'
  | 'SUBMIT_TO_DESTINATION'
  | 'APPLY_VIA_LINK'
  | 'SELF_RECORD';

export interface Provenance {
  generator: 'deterministic_rules_v1';
  ai_generated: false;
  eligibility_guaranteed: false;
  notice: string;
}

export interface MatchReason {
  code: ReasonCode;
  source_field: string;
  value: string | null;
}

export interface ContextBasis {
  memberships: { department_code: string; grade: number | null }[];
  interest_kinds: OpportunityKind[];
  interest_keywords: string[];
}

export interface RecruitmentRef {
  id: string;
  title: string;
  field: string;
  roles: string[];
  deadline_at: string;
  matched_keywords: string[];
}

export interface RecruitmentRefs {
  status: 'NOT_CONNECTED' | 'AVAILABLE' | 'UNAVAILABLE';
  open_count: number;
  items: RecruitmentRef[];
}

export interface MatchItem {
  opportunity: OpportunitySummary;
  score: number;
  reasons: MatchReason[];
  window: Window;
  freshness: Freshness;
  checked_at: string | null;
  source_url: string | null;
  recruitment: RecruitmentRefs;
}

export interface MatchPage {
  items: MatchItem[];
  next_cursor: string | null;
  candidate_cap: number;
  candidates_scanned: number;
  complete: boolean;
  omitted_count: number;
  context: ContextBasis;
  evaluated_at: string;
  provenance: Provenance;
}

export interface ProcedureStep {
  order: number;
  code: StepCode;
  available: boolean;
  evidence_field: string;
  evidence_value: string | null;
  evidence_url: string | null;
}

export interface OpportunityBrief {
  opportunity: OpportunityDetail;
  match: { in_scope: boolean; score: number; reasons: MatchReason[] };
  window: Window;
  freshness: Freshness;
  procedure: ProcedureStep[];
  cautions: { code: CautionCode }[];
  recruitment: RecruitmentRefs;
  context: ContextBasis;
  evaluated_at: string;
  provenance: Provenance;
}

export interface Interests {
  kinds: OpportunityKind[];
  keywords: string[];
}

export interface MatchFilter extends Interests {
  kind?: OpportunityKind;
  includeClosed?: boolean;
  limit?: number;
  cursor?: string;
}
