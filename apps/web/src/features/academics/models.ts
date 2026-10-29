export type SourceKind = 'DEMO' | 'OFFICIAL_PUBLIC' | 'UNKNOWN';
export type RequestKind = 'LEAVE_OF_ABSENCE' | 'RETURN_FROM_LEAVE' | 'READMISSION' | 'MAJOR_TRANSFER' | 'GRADE_CORRECTION';
export type FinalMark = 'PRESENT' | 'LATE' | 'ABSENT';
export type Mark = 'UNMARKED' | 'CHECKED_IN' | FinalMark;

export interface Provenance { source_kind: SourceKind; source_url: string | null; checked_at: string | null }
export interface Meeting { weekday: number; starts_minute: number; ends_minute: number }
export interface Offering {
  id: string; term_id: string; course_code: string; title: string; section: string; instructor_name: string;
  credits: number; capacity: number; enrolled_count: number; meetings: Meeting[]; syllabus_summary: string;
  syllabus_source: Provenance; record_source: 'DEMO';
}
export interface Enrollment { id: string; offering_id: string; term_id: string; status: 'ENROLLED' | 'DROPPED'; enrolled_at: string; dropped_at: string | null; revision: number; record_source: 'DEMO' }
export interface Grade { id: string; offering_id: string; term_id: string; course_title: string; credits: number; grade_label: string; recorded_at: string; record_source: 'DEMO' }
export interface Transcript { grades: Grade[]; listed_credit_total: number; graduation_judgement: 'NOT_PROVIDED'; official_effect: 'NONE'; record_source: 'DEMO' }
export interface AcademicRequest {
  id: string; kind: RequestKind; status: 'DRAFT' | 'SUBMITTED' | 'WITHDRAWN';
  target_term_id: string | null; target_department_id: string | null; target_grade_id: string | null; reason: string | null;
  created_at: string; updated_at: string; submitted_at: string | null; withdrawn_at: string | null; revision: number;
  review_state: 'NOT_CONNECTED'; official_effect: 'NONE'; record_source: 'DEMO';
}
export interface AttendanceOffering { offering_id: string; title: string; role: 'student' | 'teacher'; record_source: 'DEMO' }
export interface Session {
  id: string; offering_id: string; label: string; status: 'OPEN' | 'CLOSED'; opened_at: string; check_in_closes_at: string;
  closed_at: string | null; revision: number; check_in_code: string | null; record_source: 'DEMO';
}
export interface AttendanceRecord {
  id: string | null; session_id: string; member_ref: string | null; student_label: string | null; mark: Mark;
  checked_in_at: string | null; updated_at: string | null; revision: number; is_mine: boolean; judgement: 'DEMO_DISPLAY_ONLY';
}
export interface Correction {
  id: string; record_id: string; session_id: string; requested_mark: FinalMark; reason: string; status: 'REQUESTED' | 'ACCEPTED' | 'REJECTED';
  created_at: string; resolved_at: string | null; revision: number; is_mine: boolean; student_label: string | null;
}
export interface MyAttendance { sessions: Session[]; records: AttendanceRecord[]; corrections: Correction[]; record_source: 'DEMO' }
export interface Window { opens_at: string; closes_at: string }
export interface DemoPolicy {
  policy_id: string; label: string; registration_windows: Record<string, Window>; request_windows: Record<string, Window>;
  max_credits_per_term: number; check_in_window_minutes: number; check_in_attempt_limit: number;
  policy_source: 'DEMO'; school_rules: 'NOT_CONNECTED'; blocked: string[];
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const isUuid = (v: unknown): v is string => typeof v === 'string' && UUID.test(v);
const nUuid = (v: unknown) => v === null || isUuid(v);
const str = (v: unknown, max: number): v is string => typeof v === 'string' && v.length <= max;
const int = (v: unknown, min = 0, max = 100_000): v is number => Number.isInteger(v) && Number(v) >= min && Number(v) <= max;
const date = (v: unknown): v is string => typeof v === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v));
const nDate = (v: unknown) => v === null || date(v);
const oneOf = <T extends string>(v: unknown, values: readonly T[]): v is T => typeof v === 'string' && (values as readonly string[]).includes(v);
const rec = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
function list<T>(v: unknown, guard: (x: unknown) => x is T, max = 100): v is T[] { return Array.isArray(v) && v.length <= max && v.every(guard); }

export const KINDS = ['LEAVE_OF_ABSENCE', 'RETURN_FROM_LEAVE', 'READMISSION', 'MAJOR_TRANSFER', 'GRADE_CORRECTION'] as const;
const MARKS = ['UNMARKED', 'CHECKED_IN', 'PRESENT', 'LATE', 'ABSENT'] as const;
const FINAL = ['PRESENT', 'LATE', 'ABSENT'] as const;
const PRIVATE_KEYS = ['student_id', 'actor_id', 'failed_attempts'];
const noPrivate = (v: Record<string, unknown>) => PRIVATE_KEYS.every(key => !(key in v));

/** Only a fully cited OFFICIAL_PUBLIC https record is linkable; DEMO/UNKNOWN never link. */
export function officialLink(p: Provenance): { url: string; checkedAt: string } | null {
  if (p.source_kind !== 'OFFICIAL_PUBLIC' || !p.source_url || !p.checked_at || !date(p.checked_at)) return null;
  try {
    const url = new URL(p.source_url);
    if (url.protocol !== 'https:' || url.username || url.password || url.hash || p.source_url.length > 2048 || /\s/.test(p.source_url)) return null;
    return { url: url.href, checkedAt: p.checked_at };
  } catch { return null; }
}
function isProvenance(v: unknown): v is Provenance {
  if (!rec(v) || !oneOf(v.source_kind, ['DEMO', 'OFFICIAL_PUBLIC', 'UNKNOWN'] as const)) return false;
  if (!(v.source_url === null || str(v.source_url, 2048)) || !nDate(v.checked_at)) return false;
  return v.source_kind === 'OFFICIAL_PUBLIC' ? officialLink(v as unknown as Provenance) !== null : v.source_url === null && v.checked_at === null;
}
const isMeeting = (v: unknown): v is Meeting => rec(v) && int(v.weekday, 1, 7) && int(v.starts_minute, 0, 1439) && int(v.ends_minute, 1, 1440);

export function isOffering(v: unknown): v is Offering {
  return rec(v) && noPrivate(v) && isUuid(v.id) && isUuid(v.term_id) && str(v.course_code, 30) && str(v.title, 160) && str(v.section, 40)
    && str(v.instructor_name, 80) && int(v.credits, 0, 30) && int(v.capacity) && int(v.enrolled_count) && list(v.meetings, isMeeting, 14)
    && str(v.syllabus_summary, 4000) && isProvenance(v.syllabus_source) && v.record_source === 'DEMO';
}
export const isOfferings = (v: unknown): v is Offering[] => list(v, isOffering);
export function isEnrollment(v: unknown): v is Enrollment {
  return rec(v) && noPrivate(v) && isUuid(v.id) && isUuid(v.offering_id) && isUuid(v.term_id) && oneOf(v.status, ['ENROLLED', 'DROPPED'] as const)
    && date(v.enrolled_at) && nDate(v.dropped_at) && int(v.revision, 1) && v.record_source === 'DEMO';
}
export const isEnrollments = (v: unknown): v is Enrollment[] => list(v, isEnrollment, 200);
const isGrade = (v: unknown): v is Grade => rec(v) && noPrivate(v) && isUuid(v.id) && isUuid(v.offering_id) && isUuid(v.term_id)
  && str(v.course_title, 160) && int(v.credits, 0, 30) && str(v.grade_label, 10) && date(v.recorded_at) && v.record_source === 'DEMO';
export function isTranscript(v: unknown): v is Transcript {
  return rec(v) && list(v.grades, isGrade, 500) && int(v.listed_credit_total) && v.graduation_judgement === 'NOT_PROVIDED'
    && v.official_effect === 'NONE' && v.record_source === 'DEMO';
}
export function isRequest(v: unknown): v is AcademicRequest {
  return rec(v) && noPrivate(v) && isUuid(v.id) && oneOf(v.kind, KINDS) && oneOf(v.status, ['DRAFT', 'SUBMITTED', 'WITHDRAWN'] as const)
    && nUuid(v.target_term_id) && nUuid(v.target_department_id) && nUuid(v.target_grade_id) && (v.reason === null || str(v.reason, 2000))
    && date(v.created_at) && date(v.updated_at) && nDate(v.submitted_at) && nDate(v.withdrawn_at) && int(v.revision, 1)
    && v.review_state === 'NOT_CONNECTED' && v.official_effect === 'NONE' && v.record_source === 'DEMO';
}
export const isRequests = (v: unknown): v is AcademicRequest[] => list(v, isRequest, 200);
const isAttOffering = (v: unknown): v is AttendanceOffering => rec(v) && isUuid(v.offering_id) && str(v.title, 160) && oneOf(v.role, ['student', 'teacher'] as const) && v.record_source === 'DEMO';
export const isAttOfferings = (v: unknown): v is AttendanceOffering[] => list(v, isAttOffering);
export function isSession(v: unknown): v is Session {
  return rec(v) && isUuid(v.id) && isUuid(v.offering_id) && str(v.label, 80) && oneOf(v.status, ['OPEN', 'CLOSED'] as const) && date(v.opened_at)
    && date(v.check_in_closes_at) && nDate(v.closed_at) && int(v.revision, 1) && (v.check_in_code === null || (typeof v.check_in_code === 'string' && /^\d{6}$/.test(v.check_in_code)))
    && v.record_source === 'DEMO';
}
export const isSessions = (v: unknown): v is Session[] => list(v, isSession, 200);
export function isRecord(v: unknown): v is AttendanceRecord {
  return rec(v) && noPrivate(v) && nUuid(v.id) && isUuid(v.session_id) && nUuid(v.member_ref) && (v.student_label === null || str(v.student_label, 80))
    && oneOf(v.mark, MARKS) && nDate(v.checked_in_at) && nDate(v.updated_at) && int(v.revision, 0) && typeof v.is_mine === 'boolean' && v.judgement === 'DEMO_DISPLAY_ONLY';
}
export const isRecords = (v: unknown): v is AttendanceRecord[] => list(v, isRecord, 500);
export function isCorrection(v: unknown): v is Correction {
  return rec(v) && noPrivate(v) && isUuid(v.id) && isUuid(v.record_id) && isUuid(v.session_id) && oneOf(v.requested_mark, FINAL) && str(v.reason, 1000)
    && oneOf(v.status, ['REQUESTED', 'ACCEPTED', 'REJECTED'] as const) && date(v.created_at) && nDate(v.resolved_at) && int(v.revision, 1)
    && typeof v.is_mine === 'boolean' && (v.student_label === null || str(v.student_label, 80));
}
export const isCorrections = (v: unknown): v is Correction[] => list(v, isCorrection, 500);
export function isMyAttendance(v: unknown): v is MyAttendance {
  return rec(v) && list(v.sessions, isSession, 200) && v.sessions.every(s => s.check_in_code === null) && isRecords(v.records)
    && isCorrections(v.corrections) && v.record_source === 'DEMO';
}
const isWindow = (v: unknown): v is Window => rec(v) && date(v.opens_at) && date(v.closes_at);
const windows = (v: unknown) => rec(v) && Object.keys(v).length <= 50 && Object.values(v).every(isWindow);
export function isPolicy(v: unknown): v is DemoPolicy {
  return rec(v) && str(v.policy_id, 100) && str(v.label, 200) && windows(v.registration_windows) && windows(v.request_windows)
    && int(v.max_credits_per_term, 1) && int(v.check_in_window_minutes, 1) && int(v.check_in_attempt_limit, 1)
    && v.policy_source === 'DEMO' && v.school_rules === 'NOT_CONNECTED' && list(v.blocked, (x): x is string => str(x, 60), 20);
}

export const KIND_LABEL: Record<RequestKind, string> = {
  LEAVE_OF_ABSENCE: '휴학', RETURN_FROM_LEAVE: '복학', READMISSION: '재입학', MAJOR_TRANSFER: '전과', GRADE_CORRECTION: '성적 정정',
};
export const MARK_LABEL: Record<Mark, string> = { UNMARKED: '미기록', CHECKED_IN: '체크인(교수 확인 전)', PRESENT: '출석', LATE: '지각', ABSENT: '결석' };
export function targetField(kind: RequestKind): 'target_term_id' | 'target_department_id' | 'target_grade_id' {
  return kind === 'MAJOR_TRANSFER' ? 'target_department_id' : kind === 'GRADE_CORRECTION' ? 'target_grade_id' : 'target_term_id';
}
