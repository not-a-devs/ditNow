import { ApiError, requestData } from '../../lib/api';

export type EditableField = 'skills' | 'interests' | 'bio';
export interface ActivityFields { skills: string[]; interests: string[]; bio: string }
export interface Profile extends ActivityFields {
  display_name: string; department_name: string; academic_year: number; revision: number; updated_at: string;
  policy: { revision: number; editable_fields: EditableField[]; record_source: 'DEMO' };
  record_source: 'DEMO'; visibility: 'SELF_ONLY'; identity_editable: false; replayed: boolean;
}
export interface Update extends ActivityFields { expected_revision: number; expected_policy_revision: number }
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const only = (value: Record<string, unknown>, keys: string[]) => Object.keys(value).every(key => keys.includes(key));
const text = (value: unknown, max: number, empty = false): value is string => typeof value === 'string'
  && value.length <= max * 2 && (empty || value.trim().length > 0) && Array.from(value).length <= max;
const int = (value: unknown, max = 1_000_000): value is number => Number.isInteger(value) && Number(value) >= 1 && Number(value) <= max;
const tags = (value: unknown): value is string[] => Array.isArray(value) && value.length <= 20
  && value.every(item => text(item, 30) && item === item.trim() && !/[\u0000-\u001f]/.test(item))
  && new Set(value.map(item => item.toLocaleLowerCase())).size === value.length;
export function isProfile(value: unknown): value is Profile {
  if (!object(value) || !only(value, ['display_name', 'department_name', 'academic_year', 'revision', 'updated_at', 'policy', 'skills', 'interests', 'bio', 'record_source', 'visibility', 'identity_editable', 'replayed'])) return false;
  const policy = value.policy;
  return text(value.display_name, 200) && text(value.department_name, 200) && int(value.academic_year, 20)
    && int(value.revision) && typeof value.updated_at === 'string'
    && /T.*(?:Z|[+-]\d\d:\d\d)$/.test(value.updated_at) && Number.isFinite(Date.parse(value.updated_at))
    && tags(value.skills) && tags(value.interests) && text(value.bio, 500, true)
    && value.record_source === 'DEMO' && value.visibility === 'SELF_ONLY' && value.identity_editable === false
    && typeof value.replayed === 'boolean' && object(policy) && only(policy, ['revision', 'editable_fields', 'record_source'])
    && int(policy.revision) && policy.record_source === 'DEMO' && Array.isArray(policy.editable_fields)
    && policy.editable_fields.length <= 3 && policy.editable_fields.every(field => ['skills', 'interests', 'bio'].includes(field))
    && new Set(policy.editable_fields).size === policy.editable_fields.length;
}
async function checked(init?: RequestInit) {
  const data = await requestData<unknown>('/profiles/me', { cache: 'no-store', ...init });
  if (!isProfile(data)) throw new ApiError('INVALID_RESPONSE', 200);
  return data;
}
export const loadProfile = (signal?: AbortSignal) => checked({ signal });
export const saveProfile = (body: Update, key: string, signal?: AbortSignal) => checked({
  method: 'PUT', signal, headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key }, body: JSON.stringify(body),
});
export function intentTracker(generate = () => crypto.randomUUID()) {
  let prior: { body: string; key: string } | null = null;
  return { key(body: Update) { const serialized = JSON.stringify(body); if (prior?.body !== serialized) prior = { body: serialized, key: generate() }; return prior!.key; }, clear() { prior = null; } };
}
