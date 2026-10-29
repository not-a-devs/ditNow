export interface Offering {
  id: string; title: string; term: string; section: string; instructor_name: string; source_kind: 'DEMO';
}
export interface Material { id: string; title: string; description: string; public_reference_url: string | null; status: 'published'; }
export interface Assignment { id: string; title: string; instructions: string; deadline_at: string; status: 'draft' | 'published' | 'closed'; revision: number; }
export interface Question { id: string; text: string; answer: string | null; state: 'open' | 'answered' | 'resolved'; visibility: 'teacher_only'; created_at: string; revision: number; is_mine: boolean; }
export interface Submission { assignment_id: string; text: string; state: 'submitted' | 'resubmitted'; submitted_at: string; revision: number; source_kind: 'DEMO'; }
export interface Workspace { offering: Offering; role: 'student' | 'teacher'; materials: Material[]; assignments: Assignment[]; questions: Question[]; submissions: Submission[]; source_kind: 'DEMO'; }

const uuid = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
const text = (value: unknown, max: number): value is string => typeof value === 'string' && value.length <= max;
const revision = (value: unknown): value is number => Number.isInteger(value) && Number(value) >= 1;
const date = (value: unknown): value is string => typeof value === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
function list<T>(value: unknown, guard: (value: unknown) => value is T): value is T[] { return Array.isArray(value) && value.length <= 100 && value.every(guard); }

export function isOffering(value: unknown): value is Offering {
  return record(value) && uuid(value.id) && text(value.title, 160) && text(value.term, 60) && text(value.section, 40) && text(value.instructor_name, 80) && value.source_kind === 'DEMO';
}
export function isOfferings(value: unknown): value is Offering[] { return list(value, isOffering); }
export function isQuestion(value: unknown): value is Question {
  return record(value) && uuid(value.id) && text(value.text, 2000) && (value.answer === null || text(value.answer, 2000)) && ['open', 'answered', 'resolved'].includes(String(value.state)) && value.visibility === 'teacher_only' && date(value.created_at) && revision(value.revision) && typeof value.is_mine === 'boolean' && !('author_id' in value);
}
export function isSubmission(value: unknown): value is Submission {
  return record(value) && uuid(value.assignment_id) && text(value.text, 2000) && ['submitted', 'resubmitted'].includes(String(value.state)) && date(value.submitted_at) && revision(value.revision) && value.source_kind === 'DEMO';
}
export function publicReference(value: unknown): value is string {
  if (typeof value !== 'string') return false;
  try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password && !url.search && !url.hash; } catch { return false; }
}
export function isWorkspace(value: unknown): value is Workspace {
  if (!record(value) || !isOffering(value.offering) || !['student', 'teacher'].includes(String(value.role)) || value.source_kind !== 'DEMO') return false;
  return list(value.questions, isQuestion) && list(value.submissions, isSubmission)
    && list(value.materials, (m): m is Material => record(m) && uuid(m.id) && text(m.title, 160) && text(m.description, 2000) && m.status === 'published' && (m.public_reference_url === null || publicReference(m.public_reference_url)))
    && list(value.assignments, (a): a is Assignment => record(a) && uuid(a.id) && text(a.title, 160) && text(a.instructions, 5000) && date(a.deadline_at) && ['draft', 'published', 'closed'].includes(String(a.status)) && revision(a.revision));
}
