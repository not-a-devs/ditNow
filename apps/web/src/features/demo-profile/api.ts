import { ApiError, requestData } from '../../lib/api';

export const INTERESTS = ['coding', 'design', 'volunteering', 'career'] as const;
export const SKILL_LEVELS = ['beginner', 'intermediate'] as const;
export type Interest = typeof INTERESTS[number];
export type SkillLevel = typeof SKILL_LEVELS[number];
export interface Preferences { interests: Interest[]; skill_level: SkillLevel }
export interface DemoPreferences extends Preferences { revision: number; record_source: 'DEMO'; storage: 'PROCESS_MEMORY' }
export interface Update extends Preferences { revision: number }

const PATH = '/me/demo-profile';
const KEYS = ['interests', 'skill_level', 'revision', 'record_source', 'storage'];
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
export function isDemoPreferences(value: unknown): value is DemoPreferences {
  if (!object(value) || Object.keys(value).length !== KEYS.length || !KEYS.every(key => Object.hasOwn(value, key))) return false;
  const interests = value.interests;
  return Array.isArray(interests) && interests.length <= INTERESTS.length
    && interests.every(item => (INTERESTS as readonly unknown[]).includes(item)) && new Set(interests).size === interests.length
    && (SKILL_LEVELS as readonly unknown[]).includes(value.skill_level)
    && Number.isInteger(value.revision) && Number(value.revision) >= 1 && Number(value.revision) <= 1_000_001
    && value.record_source === 'DEMO' && value.storage === 'PROCESS_MEMORY';
}
/** Canonical server order, so the confirm summary and readback compare equal. */
export const canonical = (values: Interest[]) => INTERESTS.filter(item => values.includes(item));
async function checked(init: RequestInit) {
  const data = await requestData<unknown>(PATH, { cache: 'no-store', ...init });
  if (!isDemoPreferences(data)) throw new ApiError('INVALID_RESPONSE', 200);
  return data;
}
export const loadDemoProfile = (signal?: AbortSignal) => checked({ signal });
export const saveDemoProfile = (body: Update, signal?: AbortSignal) => checked({
  method: 'PATCH', signal, headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ interests: canonical(body.interests), skill_level: body.skill_level, revision: body.revision }),
});
