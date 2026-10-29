import type { Database, Role, SessionUser, User } from '../../types';
import { readDb } from '../store';

// 사전 MVP의 "서버" 계층. 화면은 이 api 함수만 호출하고 저장소를 직접 만지지 않는다.
// 권한·입력 검증을 여기서 강제해 두면 Supabase RLS/Edge Function으로 옮길 때 기준이 된다.

export type ErrorCode = 'UNAUTHORIZED' | 'FORBIDDEN' | 'VALIDATION' | 'NOT_FOUND' | 'CONFLICT';

export class ApiError extends Error {
  constructor(
    public code: ErrorCode,
    message: string,
    public fieldErrors?: Record<string, string>,
  ) {
    super(message);
  }
}

const SESSION_KEY = 'ditnow.session';

/** 탭마다 다른 계정으로 시연할 수 있도록 sessionStorage에 보관 */
export function getSessionUserId(): string | null {
  try {
    return sessionStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

export function setSessionUserId(id: string | null) {
  try {
    if (id) sessionStorage.setItem(SESSION_KEY, id);
    else sessionStorage.removeItem(SESSION_KEY);
  } catch {
    // 저장 불가 환경 — 무시
  }
}

/** 네트워크 지연을 흉내 내 로딩 상태가 실제로 보이게 한다 */
export function latency<T>(fn: () => T, ms = 120 + Math.random() * 180): Promise<T> {
  return new Promise((resolve, reject) => {
    setTimeout(() => {
      try {
        resolve(fn());
      } catch (e) {
        reject(e);
      }
    }, ms);
  });
}

export function toSessionUser(db: Database, user: User): SessionUser {
  const dept = db.departments.find((d) => d.id === user.departmentId);
  return { ...user, departmentName: dept?.name ?? '소속 없음' };
}

export function requireUser(db: Database = readDb()): User {
  const id = getSessionUserId();
  const user = id ? db.users.find((u) => u.id === id) : undefined;
  if (!user) throw new ApiError('UNAUTHORIZED', '로그인이 필요합니다. 다시 로그인해 주세요.');
  return user;
}

export function requireRole(user: User, roles: Role[]) {
  if (!roles.includes(user.role)) throw new ApiError('FORBIDDEN', '이 기능을 사용할 권한이 없습니다.');
}

export const isStaff = (user: User) => user.role === 'assistant' || user.role === 'professor' || user.role === 'admin';

/** 문자열 입력 검증: trim 후 길이 확인. 위반 시 fieldErrors에 기록 */
export function text(
  errors: Record<string, string>,
  field: string,
  label: string,
  value: unknown,
  min: number,
  max: number,
): string {
  const v = typeof value === 'string' ? value.trim() : '';
  if (v.length < min) errors[field] = min <= 1 ? `${label}을(를) 입력해 주세요.` : `${label}은(는) ${min}자 이상이어야 합니다.`;
  else if (v.length > max) errors[field] = `${label}은(는) ${max}자 이하여야 합니다.`;
  return v;
}

export function assertValid(errors: Record<string, string>) {
  if (Object.keys(errors).length > 0) throw new ApiError('VALIDATION', '입력값을 확인해 주세요.', errors);
}

export function notFound(what: string): never {
  throw new ApiError('NOT_FOUND', `${what}을(를) 찾을 수 없습니다. 삭제되었거나 접근할 수 없는 항목입니다.`);
}

export function userName(db: Database, id: string | null) {
  if (!id) return '시스템';
  return db.users.find((u) => u.id === id)?.name ?? '알 수 없음';
}

export function departmentName(db: Database, id: string | null) {
  if (!id) return '';
  return db.departments.find((d) => d.id === id)?.name ?? '';
}

export const roleLabel: Record<Role, string> = {
  student: '학생',
  assistant: '조교',
  professor: '교수',
  admin: '관리자',
};
