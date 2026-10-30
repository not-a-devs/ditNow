// FR-ATT-003/004 DEMO sandbox: synthetic mobile card + fictional numeric-code check-in.
// Server state is PROCESS_MEMORY (resets on restart); this is not a real student ID, QR/Bluetooth
// verification or attendance record. Everything resets when the session generation changes.
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '../../lib/api';
import {
  DEMO_CODE_PATTERN,
  checkInDemo,
  getDemoCard,
  getDemoState,
  type DemoAttendanceState,
  type DemoCardView,
} from './api';

export interface DemoAttendanceProps {
  sessionGeneration: number;
}

export default function DemoAttendance({ sessionGeneration }: DemoAttendanceProps) {
  // A new key discards every piece of state and in-flight reply from the previous session.
  return <DemoAttendancePanel key={sessionGeneration} />;
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 422) return '시연 코드가 일치하지 않습니다.';
  if (error instanceof ApiError && error.status === 400) return '6자리 숫자 코드를 입력하세요.';
  if (error instanceof Error && error.message) return error.message;
  return '요청을 처리하지 못했습니다.';
}

function formatTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString('ko-KR');
}

function DemoAttendancePanel() {
  const alive = useRef(true);
  const submitAbort = useRef<AbortController | null>(null);
  const submitLocked = useRef(false);
  const [view, setView] = useState<DemoCardView | null>(null);
  const [state, setState] = useState<DemoAttendanceState | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    alive.current = true;
    const controller = new AbortController();
    Promise.all([getDemoCard(controller.signal), getDemoState(controller.signal)]).then(
      ([card, current]) => {
        if (!alive.current || controller.signal.aborted) return;
        setView(card);
        setState(current);
      },
      (error: unknown) => {
        if (!alive.current || controller.signal.aborted) return;
        setLoadError(errorMessage(error));
      },
    );
    return () => {
      alive.current = false;
      controller.abort();
      submitAbort.current?.abort();
      submitAbort.current = null;
    };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitLocked.current) return;
    setNotice(null);
    setFailure(null);
    if (!DEMO_CODE_PATTERN.test(code)) {
      setFailure('6자리 숫자 코드를 입력하세요.');
      return;
    }
    const controller = new AbortController();
    submitLocked.current = true;
    submitAbort.current = controller;
    setSubmitting(true);
    try {
      const result = await checkInDemo(code, controller.signal);
      if (!alive.current || controller.signal.aborted) return;
      setState({
        mode: 'DEMO',
        storage: 'PROCESS_MEMORY',
        method: 'NUMERIC_CODE_SIMULATION',
        checked_in: true,
        checked_in_at: result.checked_in_at,
      });
      setNotice(result.replayed ? '이미 시연 출석이 기록되어 있습니다.' : '시연 출석이 기록되었습니다.');
      setCode('');
    } catch (error) {
      if (!alive.current || controller.signal.aborted) return;
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        setView(null); setState(null); setCode(''); setNotice(null); setFailure(null);
        setLoadError(errorMessage(error));
      } else setFailure(errorMessage(error));
    } finally {
      if (alive.current && submitAbort.current === controller) {
        submitAbort.current = null;
        submitLocked.current = false;
        setSubmitting(false);
      }
    }
  }

  if (loadError) {
    return (
      <section aria-labelledby="demo-attendance-title">
        <h2 id="demo-attendance-title">DEMO 모바일 학생증·출석 연습</h2>
        <p role="alert">{loadError}</p>
      </section>
    );
  }

  if (!view || !state) {
    return (
      <section aria-labelledby="demo-attendance-title" aria-busy="true">
        <h2 id="demo-attendance-title">DEMO 모바일 학생증·출석 연습</h2>
        <p>불러오는 중…</p>
      </section>
    );
  }

  return (
    <section aria-labelledby="demo-attendance-title">
      <h2 id="demo-attendance-title">DEMO 모바일 학생증·출석 연습</h2>
      <p role="note">
        <strong>DEMO · PROCESS_MEMORY</strong> 시연 전용 화면입니다. 실제 학생증·출결이 아니며 서버 재시작 시 초기화됩니다.
      </p>

      <article aria-label="DEMO 가상 학생증">
        <h3>{view.card.card_label}</h3>
        <p>{view.card.display_alias}</p>
        <p>신분 증명 효력 없음 · QR 미제공</p>
        <p>{view.card.notice}</p>
      </article>

      <article aria-label="DEMO 가상 출석">
        <h3>{view.session.session_label}</h3>
        <p>{view.session.notice}</p>
        <p>
          시뮬레이션 코드: <code>{view.session.simulation_code}</code>
        </p>
        <p aria-live="polite">
          {state.checked_in && state.checked_in_at
            ? `시연 출석 완료 (${formatTime(state.checked_in_at)})`
            : '아직 시연 출석 전입니다.'}
        </p>
        <form onSubmit={submit} noValidate>
          <label htmlFor="demo-attendance-code">6자리 시연 코드</label>
          <input
            id="demo-attendance-code"
            inputMode="numeric"
            autoComplete="off"
            maxLength={6}
            value={code}
            onChange={event => setCode(event.target.value.replace(/[^0-9]/g, '').slice(0, 6))}
            disabled={submitting}
          />
          <button type="submit" disabled={submitting}>
            {submitting ? '확인 중…' : '시연 출석'}
          </button>
        </form>
        {notice && <p role="status">{notice}</p>}
        {failure && <p role="alert">{failure}</p>}
      </article>
    </section>
  );
}
