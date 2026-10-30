import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { authFailure, conflict, markRead, readSummary, type DemoNotification, type DemoSummary } from './api';

type View = { state: 'loading' } | { state: 'error' } | { state: 'auth' } | { state: 'ready'; summary: DemoSummary };
const KIND_LABELS = { CLASS: '수업', TASK: '과제', NOTICE: '안내' } as const;

// Fictional DEMO exercise: server process memory only, in-app read state only.
// No push/email/automatic dispatch, no official read statistics, no AI generation.
export default function DemoActionCenter({ sessionGeneration }: { sessionGeneration: number }) {
  // A new session generation is a new instance: previous actor content is dropped during commit.
  return <DemoActionCenterSession key={sessionGeneration} />;
}

function DemoActionCenterSession() {
  const [view, setView] = useState<View>({ state: 'loading' });
  const [pending, setPending] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const alive = useRef(false), epoch = useRef(0), busy = useRef(false), locked = useRef(false);
  const reader = useRef<AbortController | null>(null), writer = useRef<AbortController | null>(null);

  useLayoutEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false; epoch.current++; busy.current = false;
      reader.current?.abort(); writer.current?.abort(); writer.current = null;
    };
  }, []);

  const current = (version: number, controller: AbortController) =>
    alive.current && !locked.current && version === epoch.current && !controller.signal.aborted;

  /** 401/403 latches for this generation: content is discarded and read/write/retry stay disabled. */
  function lock() {
    locked.current = true; epoch.current++; busy.current = false;
    reader.current?.abort(); writer.current?.abort(); writer.current = null;
    setPending(null); setMessage(''); setView({ state: 'auth' });
  }

  function load() {
    if (!alive.current || locked.current) return;
    reader.current?.abort(); writer.current?.abort(); writer.current = null; busy.current = false;
    const version = ++epoch.current, controller = new AbortController();
    reader.current = controller;
    setPending(null); setView({ state: 'loading' });
    readSummary(controller.signal).then(
      summary => { if (current(version, controller)) setView({ state: 'ready', summary }); },
      error => {
        if (!current(version, controller)) return;
        if (authFailure(error)) { lock(); return; }
        setMessage(''); setView({ state: 'error' });
      },
    );
  }

  useEffect(() => { load(); }, []);

  const retry = () => { if (locked.current) return; setMessage(''); load(); };

  async function read(item: DemoNotification) {
    // Same-tick latch: a second click before re-render must not send another POST.
    if (!alive.current || locked.current || busy.current) return;
    busy.current = true; reader.current?.abort();
    const version = ++epoch.current, controller = new AbortController();
    writer.current = controller;
    setPending(item.id); setMessage('');
    let posted = false, reloadAfter = false;
    try {
      const result = await markRead(item, controller.signal);
      if (!current(version, controller)) return;
      posted = true;
      const summary = await readSummary(controller.signal);
      if (!current(version, controller)) return;
      const receipt = summary.notifications.find(n => n.id === result.notification.id);
      setView({ state: 'ready', summary });
      if (!receipt || receipt.id !== item.id || !receipt.read || receipt.revision !== result.notification.revision)
        setMessage('읽음 처리 응답을 최신 목록에서 확인하지 못했습니다. 서버의 최신 상태를 표시합니다.');
    } catch (error) {
      if (!current(version, controller)) return;
      if (authFailure(error)) { lock(); return; }
      setMessage(conflict(error) ? '읽음 처리 결과를 확인하지 못했습니다. 최신 상태를 다시 불러옵니다.'
        : posted ? '읽음 처리 결과를 확인하지 못했습니다. 다시 불러와 확인해 주세요.'
        : '읽음 처리에 실패했습니다. 다시 시도해 주세요.');
      reloadAfter = conflict(error);
    } finally {
      if (alive.current && version === epoch.current) { busy.current = false; writer.current = null; setPending(null); }
    }
    if (reloadAfter) load();
  }

  return (
    <section aria-labelledby="demo-action-center-title">
      <h2 id="demo-action-center-title">가상 시연 액션 센터 (DEMO)</h2>
      <p>고정된 가상 시연 자료입니다. 실제 학사·공지 기록이 아니며 서버를 다시 시작하면 초기화됩니다. 규칙 기반 표시이며 AI가 생성하지 않았습니다.</p>
      {view.state === 'loading' && <p role="status">가상 시연 자료를 불러오는 중입니다.</p>}
      {view.state === 'error' && (
        <div role="alert">
          <p>가상 시연 자료를 불러오지 못했습니다.</p>
          <button type="button" onClick={retry}>가상 시연 다시 시도</button>
        </div>
      )}
      {view.state === 'auth' && (
        <div role="alert">
          <p>로그인 상태를 확인할 수 없어 개인 내용을 지웠습니다. 다시 로그인하면 새로 불러옵니다.</p>
        </div>
      )}
      {view.state === 'ready' && (
        <>
          <ul aria-label="가상 시연 카드">
            {view.summary.cards.map(card => (
              <li key={card.id}>
                <span>DEMO · {KIND_LABELS[card.kind]}</span> <a href={card.link}>{card.title}</a>
                <p>{card.detail}</p>
              </li>
            ))}
          </ul>
          <h3>
            앱 내 가상 알림 <span aria-label={`읽지 않은 가상 알림 ${view.summary.unread_count}건`}>{view.summary.unread_count}</span>
          </h3>
          <p>이 화면 안에서만 읽음 상태를 표시합니다. 푸시·이메일 발송이나 공식 열람 통계가 아닙니다.</p>
          {message && <p role="alert">{message}</p>}
          <ul aria-label="가상 알림">
            {view.summary.notifications.map(item => (
              <li key={item.id}>
                <a href={item.link}>{item.title}</a>
                {item.read
                  ? <span> · 읽음</span>
                  : <button type="button" disabled={pending !== null} onClick={() => void read(item)}>{item.title} 읽음 처리</button>}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
