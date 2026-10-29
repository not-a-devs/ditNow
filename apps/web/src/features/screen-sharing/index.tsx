import { useEffect, useRef, useState } from 'react';
import { isContext, isSession, isSignals, mutate, noContent, read, safeMessage, sequence, uuid, type Context, type Peer, type Session, type Signal } from './api';
import { MediaRoom } from './media';
import styles from './styles.module.css';

export default function ScreenSharingPage({ offeringId }: { offeringId?: string }) {
  return <section className={styles.page}><h1>수업 화면 공유</h1>
    <p className={styles.notice}>담당 교수의 명시적 화면 선택과 현재 수강 권한이 필요합니다. 오디오·녹음·녹화는 제공하지 않습니다. 실시간 공급자·실제 수업 송출은 아직 연결되지 않았습니다.</p>
    {offeringId && uuid(offeringId) ? <Workspace key={offeringId} offeringId={offeringId} /> : <p role="status">승인된 공통 강의실에서 분반을 연결한 뒤 사용할 수 있습니다.</p>}
  </section>;
}

function Workspace({ offeringId }: { offeringId: string }) {
  const [context, setContext] = useState<Context | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const [stream, setStream] = useState<MediaStream | null>(null); const [connected, setConnected] = useState(false);
  const [peerFailures, setPeerFailures] = useState(0);
  const video = useRef<HTMLVideoElement | null>(null);
  const control = useRef(new AbortController()); const room = useRef<MediaRoom | null>(null);
  const current = useRef<Session | null>(null); const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cursor = useRef(0); const running = useRef(false); const preparing = useRef(false);
  const intents = useRef(new Map<string, string>());
  const base = `/${offeringId}`;
  function key(path: string) { if (!intents.current.has(path)) intents.current.set(path, crypto.randomUUID()); return intents.current.get(path)!; }
  function apply(value: Context) {
    if (value.offering_id !== offeringId || (value.session && value.session.offering_id !== offeringId)) throw new Error('Wrong scope');
    current.current = value.session; setContext(value);
  }
  function stopLocal() { if (timer.current) clearTimeout(timer.current); timer.current = null; room.current?.close(); room.current = null; setConnected(false); }
  function fail() { stopLocal(); setError(safeMessage); }
  async function refresh() {
    const signal = control.current.signal;
    stopLocal(); setError(''); setBusy(true);
    try { const value = await read(base, isContext, signal); if (!signal.aborted) apply(value); }
    catch { if (!signal.aborted) { current.current = null; setContext(null); fail(); } }
    finally { if (!signal.aborted) setBusy(false); }
  }
  useEffect(() => {
    const controller = new AbortController(); control.current = controller; void refresh();
    return () => { controller.abort(); stopLocal(); };
  }, []);
  useEffect(() => { if (video.current) video.current.srcObject = stream; return () => { if (video.current) video.current.srcObject = null; }; }, [stream]);

  async function send(peer: Peer, kind: Signal['kind'], payload: string) {
    const session = current.current;
    if (!session?.me || !room.current) throw new Error('No session');
    await mutate(`${base}/sessions/${session.id}/signals`, { target_peer_id: peer.peer_id, generation: session.me.generation, target_generation: peer.generation, kind, payload }, sequence, control.current.signal, crypto.randomUUID());
  }
  async function poll() {
    if (!room.current || running.current || control.current.signal.aborted) return;
    running.current = true;
    try {
      const previous = current.current;
      const value = await read(base, isContext, control.current.signal);
      if (control.current.signal.aborted) return;
      apply(value);
      const session = value.session;
      if (!session || session.id !== previous?.id || !session.me || session.me.generation !== previous.me?.generation
        || !session.presenter || session.state !== 'LIVE' || (session.is_presenter && value.role !== 'teacher')
        || Date.parse(session.expires_at) <= Date.now()) throw new Error('Authorization changed');
      const active = room.current;
      if (!active) return;
      await active.sync(session);
      const page = await read(`${base}/sessions/${session.id}/signals?generation=${session.me.generation}&after=${cursor.current}&limit=25`, isSignals, control.current.signal);
      if (control.current.signal.aborted || room.current !== active) return;
      for (const signal of page.items) {
        if (signal.sequence <= cursor.current) throw new Error('Signal replay');
        await active.receive(signal, session); cursor.current = signal.sequence;
      }
      if (page.cursor < cursor.current) throw new Error('Invalid signal cursor'); cursor.current = page.cursor;
      if (room.current === active) timer.current = setTimeout(() => void poll(), 1500);
    } catch { if (!control.current.signal.aborted) fail(); }
    finally { running.current = false; }
  }
  async function prepare(viewer = false) {
    if (preparing.current || busy) return;
    preparing.current = true; stopLocal(); setBusy(true); setError('');
    try {
      let session = current.current;
      const path = session && session.state !== 'ENDED' ? `${base}/sessions/${session.id}/${session.me ? 'reconnect' : 'join'}` : `${base}/sessions`;
      session = await mutate(path, session?.me ? { expected_generation: session.me.generation } : null, isSession, control.current.signal, key(path));
      if (control.current.signal.aborted) return;
      if (session.offering_id !== offeringId || !session.me || !session.presenter || (!viewer && (!session.is_presenter || context?.role !== 'teacher'))) throw new Error('Wrong session');
      intents.current.delete(path); current.current = session; setContext(value => value && ({ ...value, session })); cursor.current = 0;
      setPeerFailures(0);
      room.current = new MediaRoom(!viewer, send, setStream, fail, () => void end(), () => setPeerFailures(count => count + 1));
      setConnected(true);
      if (viewer) { if (session.state !== 'LIVE') throw new Error('Not sharing'); void poll(); }
    } catch { if (!control.current.signal.aborted) fail(); }
    finally { if (!control.current.signal.aborted) setBusy(false); preparing.current = false; }
  }
  async function capture() {
    const active = room.current; const session = current.current;
    if (!active || !session?.is_presenter || !session.me || busy) return;
    setBusy(true); setError('');
    try {
      await active.chooseScreen(); // Direct click -> capture prompt, before awaiting the API.
      if (control.current.signal.aborted || room.current !== active) return;
      if (session.state === 'READY') {
        const updated = await mutate(`${base}/sessions/${session.id}/activate`, { expected_revision: session.revision }, isSession, control.current.signal);
        if (control.current.signal.aborted || room.current !== active) return;
        if (updated.id !== session.id || updated.offering_id !== offeringId || !updated.is_presenter || !updated.me || updated.state !== 'LIVE') throw new Error('Invalid activation');
        current.current = updated; setContext(value => value && ({ ...value, session: updated }));
      }
      void poll();
    } catch { if (!control.current.signal.aborted) fail(); }
    finally { if (!control.current.signal.aborted) setBusy(false); }
  }
  async function end() {
    const session = current.current; stopLocal();
    if (!session?.me) return;
    setBusy(true);
    try {
      if (session.is_presenter) await mutate(`${base}/sessions/${session.id}/end`, { expected_revision: session.revision }, isSession, control.current.signal);
      else await mutate(`${base}/sessions/${session.id}/leave`, { expected_generation: session.me.generation }, noContent, control.current.signal);
      if (!control.current.signal.aborted) await refresh();
    } catch { if (!control.current.signal.aborted) setError(safeMessage); }
    finally { if (!control.current.signal.aborted) setBusy(false); }
  }
  const session = context?.session;
  const teacher = context?.role === 'teacher' && (!session || session.state === 'ENDED' || session.is_presenter);
  return <><p>현재 분반의 서버 권한: {context?.role === 'teacher' ? '담당 교수' : context?.role === 'student' ? '수강생 · 시청 전용' : '미확인'}</p>
    {busy && <p role="status">연결 상태를 확인하고 있습니다.</p>}
    {error && <p role="alert">{error}</p>}
    {peerFailures > 0 && <p role="status">시청자 연결 {peerFailures}건을 중지했습니다. 다른 시청자의 공유는 계속되며 해당 시청자는 다시 연결해야 합니다.</p>}
    <button onClick={() => void refresh()} disabled={busy}>권한·연결 다시 확인</button>
    {context && <p>공유 상태: {session?.state ?? '세션 없음'} · 오디오 OFF · 녹화 OFF</p>}
    {teacher ? <><button disabled={busy || connected} onClick={() => void prepare()}>교수 공유 연결 준비</button><button disabled={busy || !connected || !!stream} onClick={() => void capture()}>화면 선택 · 공유 시작</button></>
      : context && <button disabled={busy || connected || session?.state !== 'LIVE'} onClick={() => void prepare(true)}>수업 화면 시청 연결</button>}
    {connected && <button onClick={() => void end()}>공유·시청 중지</button>}
    <div className={styles.media}><video ref={video} autoPlay muted playsInline controls aria-label={teacher ? '선택한 공유 화면 미리보기' : '교수 공유 화면'} />{!stream && <p>재생 중인 화면이 없습니다. 자동으로 화면을 수집하지 않습니다.</p>}</div>
    <button disabled={!stream} onClick={() => { void video.current?.requestFullscreen?.().catch(() => setError('전체화면을 지원하지 않습니다.')); }}>화면 전체 보기</button>
    <p>다시 연결할 때는 연결 준비를 반복합니다. 교수 화면 선택은 매번 직접 승인해야 하며 자동 재캡처하지 않습니다. 외부 STUN/TURN은 구성하지 않아 인터넷/NAT 환경의 연결을 보장하지 않습니다.</p>
  </>;
}
