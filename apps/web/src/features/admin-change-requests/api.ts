import { ApiError, requestData } from '../../lib/api';

export const TARGETS = ['STUDENT_DEMO_A', 'STUDENT_DEMO_B'] as const;
export const SCOPES = ['DEPARTMENT_STUDENT', 'YEAR_STUDENT'] as const;
export const REASONS = ['ACADEMIC_DEMO', 'CORRECTION_DEMO'] as const;
export const STATES = ['DRAFT', 'SUBMITTED', 'WITHDRAWN'] as const;
export type Target = typeof TARGETS[number];
export type Scope = typeof SCOPES[number];
export type Reason = typeof REASONS[number];
export type ProposalState = typeof STATES[number];
export interface CreateBody { target_code: Target; proposal_scope: Scope; reason_code: Reason; consent: true }
interface Markers { record_source: 'DEMO'; storage: 'PROCESS_MEMORY'; official_effect: false; restart_reset: true }
export interface Proposal extends Markers {
  id: string; target_code: Target; proposal_scope: Scope; reason_code: Reason; state: ProposalState; revision: number;
  created_at: string; updated_at: string; submitted_at: string | null; withdrawn_at: string | null; replayed: boolean;
}
export interface ProposalList extends Markers { items: Proposal[]; owner_cap: number }

// Same path relative to requestData, which adds the /api/v1 prefix exactly once.
const BASE = '/admin-change-requests';
const ID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const PROPOSAL_KEYS = ['id', 'target_code', 'proposal_scope', 'reason_code', 'state', 'revision', 'created_at', 'updated_at', 'submitted_at', 'withdrawn_at', 'record_source', 'storage', 'official_effect', 'restart_reset', 'replayed'];
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const exact = (value: Record<string, unknown>, keys: string[]) => Object.keys(value).length === keys.length && keys.every(key => key in value);
const oneOf = <T extends string>(list: readonly T[], value: unknown): value is T => typeof value === 'string' && (list as readonly string[]).includes(value);
const time = (value: unknown): value is string => typeof value === 'string' && /T.*(?:Z|[+-]\d\d:\d\d)$/.test(value) && Number.isFinite(Date.parse(value));
const int = (value: unknown, max = 1_000_000): value is number => Number.isInteger(value) && Number(value) >= 1 && Number(value) <= max;
const markers = (value: Record<string, unknown>) => value.record_source === 'DEMO' && value.storage === 'PROCESS_MEMORY'
  && value.official_effect === false && value.restart_reset === true;

export function isProposal(value: unknown): value is Proposal {
  if (!object(value) || !exact(value, PROPOSAL_KEYS) || !markers(value)) return false;
  return typeof value.id === 'string' && ID.test(value.id) && oneOf(TARGETS, value.target_code) && oneOf(SCOPES, value.proposal_scope)
    && oneOf(REASONS, value.reason_code) && oneOf(STATES, value.state) && int(value.revision)
    && time(value.created_at) && time(value.updated_at)
    && (value.submitted_at === null || time(value.submitted_at)) && (value.withdrawn_at === null || time(value.withdrawn_at))
    && (value.state === 'WITHDRAWN') === (value.withdrawn_at !== null) && typeof value.replayed === 'boolean';
}
export function isProposalList(value: unknown): value is ProposalList {
  if (!object(value) || !exact(value, ['items', 'owner_cap', 'record_source', 'storage', 'official_effect', 'restart_reset']) || !markers(value)) return false;
  return int(value.owner_cap, 1000) && Array.isArray(value.items) && value.items.length <= value.owner_cap
    && value.items.every(isProposal) && new Set(value.items.map(item => (item as Proposal).id)).size === value.items.length;
}

async function proposal(path: string, init: RequestInit) {
  const data = await requestData<unknown>(path, { cache: 'no-store', ...init });
  if (!isProposal(data)) throw new ApiError('INVALID_RESPONSE', 200);
  return data;
}
const json = (key: string) => ({ 'Content-Type': 'application/json', 'Idempotency-Key': key });
const safeId = (id: string) => { if (!ID.test(id)) throw new ApiError('INVALID_RESPONSE', 0); return id; };

export async function loadProposals(signal?: AbortSignal) {
  const data = await requestData<unknown>(BASE, { cache: 'no-store', signal });
  if (!isProposalList(data)) throw new ApiError('INVALID_RESPONSE', 200);
  return data;
}
// A receipt must describe exactly the requested transition, not merely be a well-formed proposal.
const reject = () => { throw new ApiError('INVALID_RESPONSE', 200); };

/** Receipt must be the same codes at DRAFT revision 1 (a manual replay may carry replayed=true). */
export async function createProposal(body: CreateBody, key: string, signal?: AbortSignal) {
  const data = await proposal(BASE, { method: 'POST', signal, headers: json(key), body: JSON.stringify(body) });
  if (data.target_code !== body.target_code || data.proposal_scope !== body.proposal_scope || data.reason_code !== body.reason_code
    || data.state !== 'DRAFT' || data.revision !== 1 || data.submitted_at !== null) reject();
  return data;
}
/** Receipt must be the same id, SUBMITTED, at expected revision + 1. */
export async function submitProposal(id: string, expectedRevision: number, key: string, signal?: AbortSignal) {
  const data = await proposal(`${BASE}/${safeId(id)}/submit`, { method: 'POST', signal, headers: json(key), body: JSON.stringify({ expected_revision: expectedRevision }) });
  if (data.id !== id || data.state !== 'SUBMITTED' || data.revision !== expectedRevision + 1 || data.submitted_at === null) reject();
  return data;
}
// DELETE carries no idempotency key: callers never retry it automatically and re-read on ambiguity.
/** Receipt must be the same id, WITHDRAWN, at revision + 1. */
export async function withdrawProposal(id: string, revision: number, signal?: AbortSignal) {
  const data = await proposal(`${BASE}/${safeId(id)}?revision=${encodeURIComponent(String(revision))}`, { method: 'DELETE', signal });
  if (data.id !== id || data.state !== 'WITHDRAWN' || data.revision !== revision + 1) reject();
  return data;
}

/** Reuses one key for the same serialized intent so a manual retry is idempotent; new intent → new key. */
export function intentTracker(generate: () => string = () => crypto.randomUUID()) {
  let prior: { intent: string; key: string } | null = null;
  return {
    key(intent: unknown) { const serialized = JSON.stringify(intent); if (prior?.intent !== serialized) prior = { intent: serialized, key: generate() }; return prior!.key; },
    clear() { prior = null; },
  };
}
/** Success is only claimed when a fresh list holds the receipt's id/state/revision. */
export const matchesReceipt = (list: ProposalList, receipt: Proposal) =>
  list.items.some(item => item.id === receipt.id && item.state === receipt.state && item.revision === receipt.revision);
