import { ApiError, requestData } from '../../lib/api';

export type Alias = '가상 지원자 A' | '가상 지원자 B' | '가상 지원자 C';
export type Motivation = 'career_exploration' | 'skill_growth' | 'project_learning';
export interface Guide { id: string; title: string; summary: string; revision: number; source_kind: 'OFFICIAL_PUBLIC' | 'DEMO' | 'UNKNOWN'; source_url: string | null; checked_at: string | null; schedules: {label: string; starts_at: string; ends_at: string}[]; faqs: {question: string; answer: string}[]; }
export interface GuidePage { items: Guide[]; offset: number; has_more: boolean; }
export interface Policy { cycle_id: string; name: string; revision: number; tracks: {id: string; label: string}[]; opens_at: string; closes_at: string; withdrawal_closes_at: string | null; max_applications: number; source_kind: 'DEMO'; }
export interface Application { id: string; cycle_id: string; demo_alias: Alias; track_id: string; motivation: Motivation; state: 'draft' | 'submitted' | 'received' | 'withdrawal_requested'; revision: number; policy_revision: number; created_at: string; updated_at: string; source_kind: 'DEMO'; documents: 'BLOCKED'; admission_result: 'BLOCKED'; payment_refund: 'BLOCKED'; }
export interface Overview { applications: Application[]; policies: Policy[]; source_kind: 'DEMO'; }
export interface Draft { cycle_id: string; track_id: string; demo_alias: Alias; motivation: Motivation; expected_policy_revision: number; }
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v) && !('owner_id' in v);
const uuid = (v: unknown): v is string => typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
const text = (v: unknown, max: number): v is string => typeof v === 'string' && v.length <= max;
const integer = (v: unknown, min = 1, max = 100000) => Number.isInteger(v) && Number(v) >= min && Number(v) <= max;
const date = (v: unknown): v is string => typeof v === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v));
const list = <T,>(v: unknown, max: number, guard: (v: unknown) => v is T): v is T[] => Array.isArray(v) && v.length <= max && v.every(guard);
export const ALIASES: Alias[] = ['가상 지원자 A', '가상 지원자 B', '가상 지원자 C'];
export const MOTIVATIONS: Record<Motivation, string> = { career_exploration: '가상 진로 탐색', skill_growth: '가상 역량 개발', project_learning: '가상 프로젝트 학습' };
export const STATES = { draft: '가상 작성 중', submitted: '가상 제출됨', received: '가상 접수 상태', withdrawal_requested: '가상 취소 요청됨' };
export function safeSource(v: unknown): v is string {
  if (typeof v !== 'string' || v.length > 2048 || /[\s\u0000-\u001f\u007f\\]/.test(v) || !/^[\x00-\x7f]*$/.test(v)) return false;
  try { const u = new URL(v); return /^https?:$/.test(u.protocol) && !!u.hostname && !u.username && !u.password && u.port !== '0'; } catch { return false; }
}
export function isGuide(v: unknown): v is Guide {
  if (!object(v) || !uuid(v.id) || !text(v.title, 200) || !text(v.summary, 1000) || !integer(v.revision)) return false;
  const citation = v.source_kind === 'OFFICIAL_PUBLIC' ? safeSource(v.source_url) && date(v.checked_at) : ['DEMO', 'UNKNOWN'].includes(String(v.source_kind)) && v.source_url === null && v.checked_at === null;
  return citation && list(v.schedules, 30, (s): s is Guide['schedules'][number] => object(s) && text(s.label, 100) && date(s.starts_at) && date(s.ends_at) && Date.parse(s.ends_at) > Date.parse(s.starts_at)) && list(v.faqs, 30, (f): f is Guide['faqs'][number] => object(f) && text(f.question, 200) && text(f.answer, 1000));
}
export function isGuidePage(v: unknown): v is GuidePage { return object(v) && list(v.items, 50, isGuide) && integer(v.offset, 0) && typeof v.has_more === 'boolean'; }
export function isApplication(v: unknown): v is Application {
  return object(v) && uuid(v.id) && uuid(v.cycle_id) && uuid(v.track_id) && ALIASES.includes(v.demo_alias as Alias) && Object.hasOwn(MOTIVATIONS, String(v.motivation)) && Object.hasOwn(STATES, String(v.state)) && integer(v.revision) && integer(v.policy_revision) && date(v.created_at) && date(v.updated_at) && v.source_kind === 'DEMO' && v.documents === 'BLOCKED' && v.admission_result === 'BLOCKED' && v.payment_refund === 'BLOCKED';
}
function isPolicy(v: unknown): v is Policy { return object(v) && uuid(v.cycle_id) && text(v.name, 100) && integer(v.revision) && list(v.tracks, 20, (t): t is Policy['tracks'][number] => object(t) && uuid(t.id) && text(t.label, 100)) && v.tracks.length > 0 && date(v.opens_at) && date(v.closes_at) && Date.parse(v.closes_at) > Date.parse(v.opens_at) && (v.withdrawal_closes_at === null || date(v.withdrawal_closes_at)) && integer(v.max_applications, 1, 20) && v.source_kind === 'DEMO'; }
export function isOverview(v: unknown): v is Overview { return object(v) && v.source_kind === 'DEMO' && list(v.applications, 100, isApplication) && list(v.policies, 20, isPolicy); }
async function checked<T>(path: string, guard: (v: unknown) => v is T, init?: RequestInit): Promise<T> { const value = await requestData<unknown>(path, init); if (!guard(value)) throw new ApiError('INVALID_RESPONSE', 200); return value; }
export const loadGuides = (signal?: AbortSignal, offset = 0) => checked(`/admissions/guides?offset=${offset}&limit=20`, isGuidePage, {signal});
export const loadOverview = (signal?: AbortSignal) => checked('/admissions/me', isOverview, {signal});
export const writeApplication = (path: string, body: object, key: string, method = 'POST') => checked(path, isApplication, {method, headers: {'Content-Type': 'application/json', 'Idempotency-Key': key}, body: JSON.stringify(body)});
export function intentTracker(generate: () => string = () => crypto.randomUUID()) {
  const attempts = new Map<string, {body: string; key: string}>();
  return { key(path: string, body: object) { const serialized = JSON.stringify(body); const old = attempts.get(path); const attempt = old?.body === serialized ? old : {body: serialized, key: generate()}; attempts.set(path, attempt); return attempt.key; }, done(path: string) { attempts.delete(path); } };
}
