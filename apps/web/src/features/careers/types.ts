// API-JOB response shapes (services/api/app/features/careers/schemas.py). The router is not
// mounted yet, so these are hand-written and every response is checked at runtime (guards.ts).
export type Provenance = 'OFFICIAL_PUBLIC' | 'DEMO' | 'UNKNOWN';
export type ApplicationStatus = 'applied' | 'cancelled';
export type EmploymentType = 'full_time' | 'part_time' | 'internship' | 'contract';

export interface JobSummary {
  id: string;
  title: string;
  organization: string;
  department_codes: string[];
  apply_starts_at: string | null;
  deadline_at: string | null;
  deadline_passed: boolean;
  provenance: Provenance;
  original_url: string | null;
  checked_at: string | null;
  platform_receives_application: false;
}

export interface JobPage { items: JobSummary[]; next_cursor: string | null }

export interface JobFilter { q?: string; department?: string; openOnly?: boolean; cursor?: string | null }

export interface ContestCandidate {
  opportunity_id: string;
  title: string;
  organization: string;
  deadline_at: string | null;
  provenance: Provenance;
  original_url: string | null;
  checked_at: string | null;
  team_link_candidate: boolean;
  reference_field: 'opportunity_id';
}

export interface ContestPage { items: ContestCandidate[]; next_cursor: string | null }

export interface CareerProfile {
  id: string;
  alias: string;
  desired_roles: string[];
  skills: string[];
  summary: string;
  revision: number;
  created_at: string;
  updated_at: string;
  shared_with: string[];
  is_virtual: true;
}

export interface ProfileInput { alias: string; desired_roles: string[]; skills: string[]; summary: string }

export interface Program {
  id: string;
  title: string;
  host: string;
  summary: string;
  capacity: number | null;
  apply_starts_at: string | null;
  apply_ends_at: string | null;
  window_open: boolean;
  provenance: Provenance;
  source_url: string | null;
  checked_at: string | null;
  accepts_virtual_application: boolean;
}

export interface ProgramList { items: Program[]; policy_id: string; policy_basis: 'DEMO' }

export interface ProgramApplication {
  id: string;
  program_id: string;
  status: ApplicationStatus;
  note: string;
  revision: number;
  created_at: string;
  updated_at: string;
  cancelled_at: string | null;
  review_status: 'not_reviewed';
  is_virtual: true;
  program: Program | null;
}

export interface EmployerDraft {
  id: string;
  company_alias: string;
  role_title: string;
  description: string;
  employment_type: EmploymentType;
  closes_at: string;
  revision: number;
  created_at: string;
  updated_at: string;
  status: 'draft';
  publishable: false;
}

export interface EmployerDraftInput {
  company_alias: string;
  role_title: string;
  description: string;
  employment_type: EmploymentType;
  closes_at: string;
}

export interface Deleted { id: string; deleted: true }
