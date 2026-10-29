// API-OPP DTOs mirrored from services/api/app/features/opportunities/schemas.py.
// Replace with generated OpenAPI types once root mounts the router and exports the snapshot.

export type OpportunityKind = 'scholarship' | 'work_study' | 'career' | 'contest' | 'event';
export type SubmissionMode = 'external_document_submission' | 'external_link' | 'info_only';
export type SourceKind = 'DEMO' | 'PUBLIC_SOURCE';
export type PreparationStatus = 'interested' | 'preparing' | 'self_reported_submitted' | 'closed';

export interface TargetScope {
  level: 'school' | 'department' | 'grade';
  department_codes: string[];
  academic_years: number[];
}

export interface OpportunitySummary {
  id: string;
  kind: OpportunityKind;
  title: string;
  organization: string;
  target_scope: TargetScope;
  apply_starts_at: string | null;
  deadline_at: string | null;
  deadline_passed: boolean;
  submission_mode: SubmissionMode;
  source_kind: SourceKind;
  needs_verification: boolean;
}

export interface OpportunityFile {
  filename: string;
  original_url: string | null;
  checked_at: string | null;
}

export interface OpportunityDetail extends OpportunitySummary {
  eligibility: string;
  destination: string | null;
  original_url: string | null;
  source_url: string | null;
  checked_at: string | null;
  files: OpportunityFile[];
  platform_receives_submission: false;
}

export interface OpportunityPage {
  items: OpportunitySummary[];
  next_cursor: string | null;
}

export interface CheckItem {
  id: string;
  text: string;
  sort_order: number;
  completed_at: string | null;
  revision: number;
}

export interface SavedOpportunity {
  opportunity_id: string;
  status: PreparationStatus;
  memo: string;
  self_reported_submitted_at: string | null;
  revision: number;
  created_at: string;
  updated_at: string;
  checks: CheckItem[];
  opportunity: OpportunitySummary | null;
}

export interface SavedOpportunityList {
  items: SavedOpportunity[];
}

export interface OpportunityFilter {
  kind?: OpportunityKind;
  q?: string;
  department?: string;
  openOnly?: boolean;
  cursor?: string;
}
