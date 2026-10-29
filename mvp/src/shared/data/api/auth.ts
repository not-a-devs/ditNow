import type { SessionUser } from '../../types';
import { readDb } from '../store';
import { ApiError, getSessionUserId, latency, roleLabel, setSessionUserId, toSessionUser } from './core';

/**
 * 시연 전용 공통 비밀번호. 사전 MVP는 실제 인증 서버가 없으므로 계정 구분만 한다.
 * Supabase Auth 연결 시 이 상수는 삭제된다 (실 서비스 비밀번호 아님).
 */
export const DEMO_PASSWORD = 'dit1234';

export function listDemoAccounts() {
  const db = readDb();
  return db.users.map((u) => {
    const s = toSessionUser(db, u);
    return {
      email: u.email,
      label: `${u.name} · ${roleLabel[u.role]}`,
      detail: u.role === 'student' ? `${s.departmentName} ${u.academicYear}학년` : u.role === 'admin' ? '학교 전체' : s.departmentName,
    };
  });
}

export function currentUser(): SessionUser | null {
  const id = getSessionUserId();
  if (!id) return null;
  const db = readDb();
  const user = db.users.find((u) => u.id === id);
  return user ? toSessionUser(db, user) : null;
}

export function login(email: string, password: string) {
  return latency(() => {
    const db = readDb();
    const user = db.users.find((u) => u.email === email.trim().toLowerCase());
    // 어떤 값이 틀렸는지 알려주지 않는다 (FR-AUTH-001)
    if (!user || password !== DEMO_PASSWORD) {
      throw new ApiError('UNAUTHORIZED', '이메일 또는 비밀번호가 올바르지 않습니다.');
    }
    setSessionUserId(user.id);
    return toSessionUser(db, user);
  });
}

export function logout() {
  setSessionUserId(null);
}
