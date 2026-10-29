import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '../../lib/api';
import { login, logout, validateCredentials, type DemoLoginSession } from './api';
import styles from './styles.module.css';

export type AuthViewState =
  | { state: 'signed_out' }
  | { state: 'expired' }
  | { state: 'signed_in'; session: DemoLoginSession };
export type SignOutReason = 'logout' | 'expired' | 'local_only';
export interface PlatformLoginProps {
  /** Activation and the sole in-memory session owner belong to the shared auth integrator. */
  enabled?: boolean;
  session: AuthViewState;
  onSignedIn: (session: DemoLoginSession) => void;
  onSignedOut: (reason: SignOutReason) => void;
}

function failure(error: unknown): string {
  if (!(error instanceof ApiError)) return '로그인 결과를 확인하지 못했습니다. 다시 시도해 주세요.';
  if (error.status === 503) return '로그인 서버·가상 계정 원장 연결이 준비되지 않았습니다. 로그인되지 않았습니다.';
  if (error.status === 401) return '학번과 비밀번호를 확인해 주세요.';
  if (error.status === 403) return '이 계정의 로그인이 허용되지 않았습니다.';
  if (error.status === 429) return '요청이 많습니다. 잠시 기다린 뒤 다시 시도해 주세요.';
  if (error.code === 'SECURE_TRANSPORT_REQUIRED') return '학번과 비밀번호를 보내려면 HTTPS 연결이 필요합니다.';
  if (error.code === 'INVALID_RESPONSE') return '서버의 가상 계정 응답을 확인하지 못했습니다. 로그인되지 않았습니다.';
  if (error.code === 'VALIDATION') return '학번과 비밀번호의 입력 범위를 확인해 주세요.';
  return '서버 응답을 확인하지 못했습니다. 자동 재시도하지 않으니 연결 상태를 확인해 주세요.';
}

export default function PlatformLogin({ enabled = false, session, onSignedIn, onSignedOut }: PlatformLoginProps) {
  const [studentId, setStudentId] = useState('');
  const [password, setPassword] = useState('');
  const [pending, setPending] = useState<'login' | 'logout' | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const alive = useRef(false), epoch = useRef(0), active = useRef<AbortController | null>(null);
  const busy = useRef(false);
  const callbacks = useRef({ onSignedIn, onSignedOut });
  callbacks.current = { onSignedIn, onSignedOut };
  const token = session.state === 'signed_in' ? session.session.token : null;

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; epoch.current++; active.current?.abort(); };
  }, []);
  useEffect(() => {
    epoch.current++;
    active.current?.abort();
    active.current = null;
    busy.current = false;
    setPending(null);
    setPassword('');
    setError('');
  }, [enabled, session.state, token]);

  function begin(kind: 'login' | 'logout') {
    if (!enabled || busy.current) return null;
    busy.current = true;
    const version = ++epoch.current;
    const controller = new AbortController();
    active.current = controller;
    setPending(kind); setError(''); setNotice('');
    return { controller, current: () => alive.current && epoch.current === version && !controller.signal.aborted };
  }
  function finish(request: { current: () => boolean }) {
    if (request.current()) { busy.current = false; active.current = null; setPending(null); }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (session.state === 'signed_in' || !enabled || busy.current) return;
    const input = { student_id: studentId.trim(), password };
    const invalid = validateCredentials(input);
    if (invalid) { setError(invalid); return; }
    const request = begin('login');
    if (!request) return;
    // Keep credentials only in this request closure; never put them in storage, URLs or logs.
    setPassword('');
    try {
      const result = await login(input, request.controller.signal);
      if (!request.current()) return;
      callbacks.current.onSignedIn(result);
    } catch (cause) {
      if (request.current()) setError(failure(cause));
    } finally { finish(request); }
  }
  async function signOut() {
    if (session.state !== 'signed_in') return;
    const request = begin('logout');
    if (!request) return;
    let reason: SignOutReason = 'logout';
    let resultNotice = '서버의 로그아웃 응답을 확인했습니다.';
    try {
      await logout(session.session.token, request.controller.signal);
    } catch (cause) {
      if (!request.current()) return;
      const expired = cause instanceof ApiError && cause.status === 401;
      resultNotice = expired ? '세션이 만료되어 이 화면의 로그인을 해제했습니다.'
        : '이 화면의 로그인은 해제합니다. 서버의 세션 폐기는 확인하지 못했습니다.';
      reason = expired ? 'expired' : 'local_only';
    }
    if (!request.current()) return;
    setNotice(resultNotice);
    finish(request);
    try { callbacks.current.onSignedOut(reason); }
    catch { setNotice(''); setError('공통 메모리 세션 해제를 완료하지 못했습니다. 보호 기능을 계속 사용하지 말고 다시 확인해 주세요.'); }
  }

  return <section className={styles.panel} aria-labelledby="platform-login-title">
    <header><p className={styles.eyebrow}>DIT NOW · 통합 플랫폼</p><h1 id="platform-login-title">가상 계정 로그인</h1></header>
    <p className={styles.provenance}>시연용 가상 계정 전용입니다. 학교의 실제 계정·SSO와 연결하지 않습니다. 승인된 시연 계정만 입력해 주세요.</p>
    {!enabled && <p role="status">공통 로그인 연결 승인 전이라 입력과 요청을 비활성화했습니다.</p>}
    {session.state === 'expired' && <p role="status">세션이 만료되었습니다. 보호 기능을 계속 사용하려면 다시 로그인해 주세요.</p>}
    {error && <p role="alert" className={styles.error}>{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {session.state === 'signed_in' ? <div className={styles.signedIn}>
      <p><strong>{session.session.name}</strong> · 가상 계정(DEMO)</p>
      <p>역할·학과·수강 권한은 서버가 요청마다 확인합니다. 이 화면은 권한을 부여하지 않습니다.</p>
      <button disabled={!enabled || pending !== null} onClick={() => void signOut()}>{pending === 'logout' ? '로그아웃 확인 중…' : '로그아웃'}</button>
    </div> : <form onSubmit={event => void submit(event)} noValidate aria-busy={pending !== null}>
      <label htmlFor="platform-student-id">가상 학번</label>
      <input id="platform-student-id" name="username" autoComplete="username" value={studentId}
        onChange={event => setStudentId(event.target.value)} disabled={!enabled || pending !== null}
        spellCheck={false} autoCapitalize="none" aria-describedby="platform-login-input-help" />
      <label htmlFor="platform-password">비밀번호</label>
      <input id="platform-password" name="password" type="password" autoComplete="current-password" value={password}
        onChange={event => setPassword(event.target.value)} disabled={!enabled || pending !== null}
        aria-describedby="platform-login-input-help" />
      <p id="platform-login-input-help" className={styles.hint}>학번 1~20자, 비밀번호 1~64자. 비밀번호는 제출 즉시 입력란에서 지웁니다. 새로고침하면 메모리 세션은 유지되지 않습니다.</p>
      <button type="submit" disabled={!enabled || pending !== null}>{pending === 'login' ? '로그인 확인 중…' : '가상 계정으로 로그인'}</button>
    </form>}
    <p className={styles.hint}>서버 미연결·실패를 로그인 성공으로 표시하지 않습니다. 가입·비밀번호 초기화·관리자 권한 부여는 이 화면에서 제공하지 않습니다.</p>
  </section>;
}
