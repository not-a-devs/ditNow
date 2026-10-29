import { useCallback, useEffect, useRef, useState } from 'react';
import { authFailure, conflict, markRead, readInbox, readSummary, SOURCE_LABELS, type Notification, type Page, type Summary, type SummaryItem } from './api';

type State<T> = { data?: T; loading: boolean; error: boolean };
const safeError = '공통 인증·권한·저장소 연결 또는 현재 상태를 확인하지 못했습니다. 다시 시도해 주세요.';
const when = (v: string) => new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Seoul' }).format(new Date(v));

// Each load aborts the previous one; only the latest, non-aborted response may update state.
function useLoad<T>(load: (signal: AbortSignal) => Promise<T>, onAuth: () => void) {
  const [state, setState] = useState<State<T>>({ loading: true, error: false });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setState(s => ({ data: s.data, loading: true, error: false }));
    load(controller.signal).then(data => { if (!controller.signal.aborted) setState({ data, loading: false, error: false }); }, error => {
      if (controller.signal.aborted) return;
      if (authFailure(error)) onAuth();
      setState({ loading: false, error: true });
    });
    return () => controller.abort();
  }, [load, tick, onAuth]);
  return { ...state, reload: useCallback(() => setTick(n => n + 1), []) };
}

function Status({ state, label }: { state: State<unknown> & { reload: () => void }; label: string }) {
  if (state.loading) return <p role="status">{label} 불러오는 중입니다.</p>;
  if (state.error) return <div role="alert"><p>{safeError}</p><button onClick={state.reload}>{label} 다시 시도</button></div>;
  return null;
}

function Items({ title, rows, empty }: { title: string; rows: SummaryItem[]; empty: string }) {
  return <section aria-label={title}><h3>{title}</h3>{rows.length === 0 ? <p>{empty}</p> : <ul>{rows.map(r =>
    <li key={r.source_id}><a href={r.link}>{r.title}</a> · {when(r.at)} · <span>{SOURCE_LABELS[r.record_source]}</span></li>)}</ul>}</section>;
}

export default function ActionCenterPage() {
  const [denied, setDenied] = useState(false);
  const [generation, setGeneration] = useState(0);
  const onAuth = useCallback(() => setDenied(true), []);
  return <section aria-labelledby="action-center-title"><h1 id="action-center-title">오늘 챙길 일과 알림</h1>
    <p>현재 권한으로 확인된 원본만 모아 보여 줍니다. 시간순 시연 정렬이며 학교 공식 우선순위가 아닙니다. 앱 안 알림만 제공하고 푸시·문자·메일은 발송하지 않습니다.</p>
    {denied ? <div role="alert"><p>현재 접근 권한을 확인하지 못해 내용을 비웠습니다.</p><button onClick={() => { setDenied(false); setGeneration(g => g + 1); }}>권한 다시 확인</button></div>
      : <Workspace key={generation} onAuth={onAuth} />}
  </section>;
}

function Workspace({ onAuth }: { onAuth: () => void }) {
  const [offset, setOffset] = useState(0);
  const summary = useLoad<Summary>(readSummary, onAuth);
  const loadInbox = useCallback((signal: AbortSignal) => readInbox(offset, signal), [offset]);
  const inbox = useLoad<Page>(loadInbox, onAuth);
  const [rows, setRows] = useState<Record<string, Notification>>({});
  const [pending, setPending] = useState<string | null>(null);
  const [readError, setReadError] = useState(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => { setRows({}); }, [inbox.data]);

  async function read(item: Notification) {
    if (request.current) return;
    const controller = new AbortController(); request.current = controller;
    setPending(item.id); setReadError(false);
    try {
      const row = await markRead(item, controller.signal);
      if (controller.signal.aborted) return;
      setRows(r => ({ ...r, [row.id]: row })); summary.reload();
    } catch (failure) {
      if (controller.signal.aborted) return;
      if (authFailure(failure)) { onAuth(); return; }
      setReadError(true); if (conflict(failure)) inbox.reload();
    } finally { if (!controller.signal.aborted) { request.current = null; setPending(null); } }
  }

  const s = summary.data;
  const page = inbox.data;
  return <>
    <section aria-label="오늘 요약"><h2>오늘 요약</h2><Status state={summary} label="오늘 요약" />
      {s && <>
        <p>{s.local_date} (UTC{s.utc_offset}) 기준 · 읽지 않은 알림 {s.unread_notifications}{s.unread_capped ? '건 이상' : '건'}</p>
        <Items title="오늘 수업" rows={s.classes} empty="오늘 확인된 수업이 없습니다." />
        <Items title="다가오는 과제" rows={s.tasks} empty="7일 안에 마감되는 과제가 없습니다." />
        <Items title="최근 공지" rows={s.notices} empty="현재 볼 수 있는 공지가 없습니다." />
        <Items title="기회 마감" rows={s.deadlines} empty="14일 안에 마감되는 저장한 기회가 없습니다." />
      </>}
    </section>
    <section aria-label="개인 알림함"><h2>개인 알림함</h2><Status state={inbox} label="알림" />
      {readError && <p role="alert">읽음 처리 결과를 확인하지 못했습니다. 최신 상태를 다시 확인해 주세요.</p>}
      {page && page.items.length === 0 && <p>표시할 알림이 없습니다.</p>}
      {page && <ul>{page.items.map(base => { const n = rows[base.id] ?? base; return <li key={n.id}>
        <a href={n.link}>{n.title}</a> · {when(n.created_at)} · <span>{SOURCE_LABELS[n.record_source]}</span> · {n.read_at ? '읽음' : '읽지 않음'}
        {!n.read_at && <button disabled={pending !== null} onClick={() => void read(n)} aria-label={`${n.title} 읽음 처리`}>{pending === n.id ? '처리 중' : '읽음 처리'}</button>}
      </li>; })}</ul>}
      <nav aria-label="알림 페이지"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}>이전</button>
        <button disabled={!page || page.next_offset === null || inbox.loading} onClick={() => page?.next_offset != null && setOffset(page.next_offset)}>다음</button></nav>
    </section>
  </>;
}
