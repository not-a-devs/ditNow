import { createContext, useCallback, useContext, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { abortAuthenticatedRequests, ApiError, registerAuthentication, requestData } from '../../lib/api';
import { isDemoLoginSession, logout, type DemoLoginSession } from './api';

export interface CurrentUser {
  user_id: string; display_name: string; record_source: 'DEMO'; department_id: string;
  department_code: string; academic_year: number; community_access: boolean;
}
const uuid = (v: unknown) => typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(v);
const text = (v: unknown, max: number) => typeof v === 'string' && v.trim().length > 0 && v.length <= max * 2 && Array.from(v).length <= max;
export function isCurrentUser(value: unknown): value is CurrentUser {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const v = value as Record<string, unknown>;
  return Object.keys(v).every(key => ['user_id', 'display_name', 'record_source', 'department_id', 'department_code', 'academic_year', 'community_access'].includes(key))
    && uuid(v.user_id) && uuid(v.department_id) && text(v.display_name, 200) && text(v.department_code, 50)
    && Number.isSafeInteger(v.academic_year) && Number(v.academic_year) > 0
    && v.record_source === 'DEMO' && typeof v.community_access === 'boolean';
}
type Phase = 'signed_out' | 'checking' | 'authenticated' | 'expired' | 'error';
interface View { phase: Phase; generation: number; user: CurrentUser | null; message: string }
interface Auth extends View {
  accept: (session: DemoLoginSession) => void;
  signOut: () => void;
}
const Context = createContext<Auth | null>(null);
export function useMemoryAuth() { const auth = useContext(Context); if (!auth) throw new Error('Memory auth provider required'); return auth; }

export function MemoryAuthProvider({ children }: { children: ReactNode }) {
  // Sole token owner; React view state and transport retain no persistent credential copy.
  const memory = useRef<{ generation: number; session: DemoLoginSession | null; verified: boolean }>({ generation: 0, session: null, verified: false });
  const alive = useRef(false), checking = useRef(false);
  const [view, setView] = useState<View>({ phase: 'signed_out', generation: 0, user: null, message: '' });
  const clear = useCallback((phase: Phase, message = '') => {
    const generation = ++memory.current.generation;
    memory.current.session = null; memory.current.verified = false; checking.current = false;
    abortAuthenticatedRequests();
    if (alive.current) setView({ phase, generation, user: null, message });
    return generation;
  }, []);
  useLayoutEffect(() => {
    alive.current = true;
    const release = registerAuthentication({
      read: () => ({ generation: memory.current.generation, token: memory.current.session?.token ?? null, verified: memory.current.verified }),
      denied: (generation, status) => {
        if (generation === memory.current.generation) clear(status === 401 ? 'expired' : 'error', status === 401 ? '세션이 만료되어 개인 데이터를 모두 지웠습니다.' : '현재 권한 확인에 실패하여 개인 데이터를 모두 지웠습니다. 다시 로그인해 주세요.');
      },
    });
    return () => { alive.current = false; memory.current.generation++; memory.current.session = null; memory.current.verified = false; checking.current = false; release(); };
  }, [clear]);
  const accept = useCallback((candidate: DemoLoginSession) => {
    if (checking.current || !isDemoLoginSession(candidate)) return;
    const generation = clear('checking'); checking.current = true;
    memory.current.session = candidate;
    void requestData<unknown>('/auth/me').then(user => {
      if (!alive.current || memory.current.generation !== generation) return;
      if (!isCurrentUser(user)) throw new ApiError('INVALID_RESPONSE', 200);
      memory.current.verified = true; checking.current = false;
      setView({ phase: 'authenticated', generation, user, message: '' });
    }).catch(error => {
      if (!alive.current || memory.current.generation !== generation) return;
      clear(error instanceof ApiError && error.status === 401 ? 'expired' : 'error',
        error instanceof ApiError && error.status === 503 ? '공통 신원·권한 서버가 준비되지 않아 로그인되지 않았습니다.' : '공통 신원·현재 권한을 확인하지 못했습니다. 로그인되지 않았습니다.');
    });
  }, [clear]);
  const signOut = useCallback(() => {
    const token = memory.current.session?.token;
    const generation = clear('signed_out', '이 브라우저의 개인 데이터를 지웠습니다.');
    if (!token) return;
    void logout(token).then(() => {
      if (alive.current && memory.current.generation === generation) setView(value => ({ ...value, message: '서버 로그아웃도 확인했습니다.' }));
    }).catch(() => {
      if (alive.current && memory.current.generation === generation) setView(value => ({ ...value, message: '개인 데이터는 지웠지만 서버 세션 폐기는 확인하지 못했습니다.' }));
    });
  }, [clear]);
  return <Context.Provider value={{ ...view, accept, signOut }}>{children}</Context.Provider>;
}
