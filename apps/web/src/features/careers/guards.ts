// Runtime response guards. requestData<T> only casts, so anything the UI renders is checked
// here first; a shape mismatch or a claim the server must never make (e.g. publishable=true,
// a review result, an http: link) becomes INVALID_RESPONSE instead of being shown.
import { ApiError } from '../../lib/api';
import type {
  CareerProfile,
  ContestCandidate,
  ContestPage,
  Deleted,
  EmployerDraft,
  JobPage,
  JobSummary,
  Program,
  ProgramApplication,
  ProgramList,
  Provenance,
} from './types';

type Rec = Record<string, unknown>;

function invalid(): never {
  throw new ApiError('INVALID_RESPONSE', 200);
}

function rec(value: unknown): Rec {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Rec) : invalid();
}

/** Length in Unicode code points, the unit the server (Python `len`) uses for its limits. */
export function codePointLength(text: string): number {
  return Array.from(text).length;
}

function str(value: unknown, max = 5000): string {
  // A code point is at most two UTF-16 units, so the cheap bound rejects huge strings first.
  return typeof value === 'string' && value.length <= max * 2 && codePointLength(value) <= max ? value : invalid();
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function id(value: unknown): string {
  const text = str(value, 36);
  return UUID.test(text) ? text : invalid();
}

function date(value: unknown): string {
  const text = str(value, 40);
  return /(?:[zZ]|[+-]\d{2}:\d{2})$/.test(text) && !Number.isNaN(Date.parse(text)) ? text : invalid();
}

function nullable<T>(value: unknown, read: (v: unknown) => T): T | null {
  return value === null ? null : read(value);
}

function bool(value: unknown): boolean {
  return typeof value === 'boolean' ? value : invalid();
}

function int(value: unknown): number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : invalid();
}

function strings(value: unknown, max = 50): string[] {
  return Array.isArray(value) && value.length <= max ? value.map((v) => str(v, 200)) : invalid();
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[]): T {
  return allowed.includes(value as T) ? (value as T) : invalid();
}

function exactly<T>(value: unknown, expected: T): T {
  return value === expected ? expected : invalid();
}

function list<T>(value: unknown, read: (v: unknown) => T): T[] {
  return Array.isArray(value) && value.length <= 200 ? value.map(read) : invalid();
}

/** Only absolute https links are rendered as anchors; anything else is dropped to text. */
export function safeHref(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password ? url.href : null;
  } catch {
    return null;
  }
}

const PROVENANCE: readonly Provenance[] = ['OFFICIAL_PUBLIC', 'DEMO', 'UNKNOWN'];

function provenance(value: unknown, url: string | null, checked: string | null): Provenance {
  const kind = oneOf(value, PROVENANCE);
  // An official label without a link and a checked date is not trustworthy: show as UNKNOWN.
  return kind === 'OFFICIAL_PUBLIC' && (!safeHref(url) || !checked) ? 'UNKNOWN' : kind;
}

function cursor(value: unknown): string | null {
  return nullable(value, (v) => str(v, 200));
}

export function jobSummary(value: unknown): JobSummary {
  const r = rec(value);
  const original_url = nullable(r.original_url, (v) => str(v, 2048));
  const checked_at = nullable(r.checked_at, date);
  return {
    id: id(r.id),
    title: str(r.title, 300),
    organization: str(r.organization, 300),
    department_codes: strings(r.department_codes),
    apply_starts_at: nullable(r.apply_starts_at, date),
    deadline_at: nullable(r.deadline_at, date),
    deadline_passed: bool(r.deadline_passed),
    provenance: provenance(r.provenance, original_url, checked_at),
    original_url: safeHref(original_url),
    checked_at,
    platform_receives_application: exactly(r.platform_receives_application, false as const),
  };
}

export function jobPage(value: unknown): JobPage {
  const r = rec(value);
  return { items: list(r.items, jobSummary), next_cursor: cursor(r.next_cursor) };
}

export function contestCandidate(value: unknown): ContestCandidate {
  const r = rec(value);
  const original_url = nullable(r.original_url, (v) => str(v, 2048));
  const checked_at = nullable(r.checked_at, date);
  return {
    opportunity_id: id(r.opportunity_id),
    title: str(r.title, 300),
    organization: str(r.organization, 300),
    deadline_at: nullable(r.deadline_at, date),
    provenance: provenance(r.provenance, original_url, checked_at),
    original_url: safeHref(original_url),
    checked_at,
    team_link_candidate: bool(r.team_link_candidate),
    reference_field: exactly(r.reference_field, 'opportunity_id' as const),
  };
}

export function contestPage(value: unknown): ContestPage {
  const r = rec(value);
  return { items: list(r.items, contestCandidate), next_cursor: cursor(r.next_cursor) };
}

export function profile(value: unknown): CareerProfile {
  const r = rec(value);
  return {
    id: id(r.id),
    alias: str(r.alias, 30),
    desired_roles: strings(r.desired_roles, 5),
    skills: strings(r.skills, 20),
    summary: str(r.summary, 500),
    revision: int(r.revision),
    created_at: date(r.created_at),
    updated_at: date(r.updated_at),
    // Sharing is BLOCKED; a non-empty list would be a false claim.
    shared_with: Array.isArray(r.shared_with) && r.shared_with.length === 0 ? [] : invalid(),
    is_virtual: exactly(r.is_virtual, true as const),
  };
}

export function profileEnvelope(value: unknown): CareerProfile | null {
  const r = rec(value);
  return nullable(r.profile, profile);
}

export function program(value: unknown): Program {
  const r = rec(value);
  const source_url = nullable(r.source_url, (v) => str(v, 2048));
  const checked_at = nullable(r.checked_at, date);
  const kind = provenance(r.provenance, source_url, checked_at);
  return {
    id: id(r.id),
    title: str(r.title, 300),
    host: str(r.host, 300),
    summary: str(r.summary, 2000),
    capacity: nullable(r.capacity, int),
    apply_starts_at: nullable(r.apply_starts_at, date),
    apply_ends_at: nullable(r.apply_ends_at, date),
    window_open: bool(r.window_open),
    provenance: kind,
    source_url: safeHref(source_url),
    checked_at,
    // Virtual applications are only ever offered for DEMO programs.
    accepts_virtual_application: bool(r.accepts_virtual_application) && kind === 'DEMO',
  };
}

export function programList(value: unknown): ProgramList {
  const r = rec(value);
  return {
    items: list(r.items, program),
    policy_id: str(r.policy_id, 64),
    policy_basis: exactly(r.policy_basis, 'DEMO' as const),
  };
}

export function application(value: unknown): ProgramApplication {
  const r = rec(value);
  return {
    id: id(r.id),
    program_id: id(r.program_id),
    status: oneOf(r.status, ['applied', 'cancelled'] as const),
    note: str(r.note, 200),
    revision: int(r.revision),
    created_at: date(r.created_at),
    updated_at: date(r.updated_at),
    cancelled_at: nullable(r.cancelled_at, date),
    review_status: exactly(r.review_status, 'not_reviewed' as const),
    is_virtual: exactly(r.is_virtual, true as const),
    program: nullable(r.program, program),
  };
}

export function applicationList(value: unknown): ProgramApplication[] {
  return list(rec(value).items, application);
}

export function employerDraft(value: unknown): EmployerDraft {
  const r = rec(value);
  return {
    id: id(r.id),
    company_alias: str(r.company_alias, 30),
    role_title: str(r.role_title, 80),
    description: str(r.description, 2000),
    employment_type: oneOf(r.employment_type, ['full_time', 'part_time', 'internship', 'contract'] as const),
    closes_at: date(r.closes_at),
    revision: int(r.revision),
    created_at: date(r.created_at),
    updated_at: date(r.updated_at),
    status: exactly(r.status, 'draft' as const),
    publishable: exactly(r.publishable, false as const),
  };
}

export function employerDraftList(value: unknown): EmployerDraft[] {
  return list(rec(value).items, employerDraft);
}

export function deleted(value: unknown): Deleted {
  const r = rec(value);
  return { id: id(r.id), deleted: exactly(r.deleted, true as const) };
}
