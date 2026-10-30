import { useLayoutEffect, useRef, useState } from 'react';
import { MediaRoom } from './media';
import styles from './styles.module.css';

/**
 * Dormant local-only preview (not mounted by any router). It never creates peers, signals,
 * uploads, records or grants presenter rights: `MediaRoom.sync/receive` are never called.
 */
type Status = 'IDLE' | 'CHOOSING' | 'PREVIEW' | 'STOPPED' | 'ENDED' | 'DENIED';

const noSend = async () => {};
const messages: Partial<Record<Status, string>> = {
  CHOOSING: '브라우저 창에서 미리 볼 화면을 직접 선택하세요.',
  STOPPED: '로컬 미리보기를 중지했습니다.',
  ENDED: '브라우저에서 화면 공유가 중지되어 로컬 미리보기를 종료했습니다.',
  DENIED: '화면 선택이 취소되었거나 허용되지 않았습니다. 다시 시도할 수 있습니다.',
};

export function previewSupported(): boolean {
  if (typeof window === 'undefined' || !window.isSecureContext || typeof navigator === 'undefined') return false;
  const nav = navigator as Navigator & { userAgentData?: { mobile?: boolean } };
  if (nav.userAgentData?.mobile || /Android|iPhone|iPad|iPod|Mobile/i.test(nav.userAgent ?? '')) return false;
  return typeof nav.mediaDevices?.getDisplayMedia === 'function';
}

export default function LocalScreenPreview({ sessionGeneration }: { sessionGeneration?: number }) {
  return <section className={styles.page} aria-label="로컬 화면 미리보기">
    <h2>내 화면 로컬 미리보기</h2>
    <p className={styles.notice}>이 화면은 내 브라우저 안에서만 보이는 로컬 미리보기입니다. 실제 수업 시청 화면이 아니며, 네트워크로 전송·송출·녹화·저장하지 않고 교수 공유 권한을 부여하지 않습니다. 오디오는 포함하지 않습니다.</p>
    <Preview key={sessionGeneration ?? 0} />
  </section>;
}

function Preview() {
  const [status, setStatus] = useState<Status>('IDLE');
  const [stream, setStream] = useState<MediaStream | null>(null);
  const video = useRef<HTMLVideoElement | null>(null);
  const room = useRef<MediaRoom | null>(null);
  const busy = useRef(false); const epoch = useRef(0);
  const supported = previewSupported();

  function close() {
    const instance = room.current; room.current = null; epoch.current += 1;
    instance?.close();
    if (video.current) video.current.srcObject = null;
  }
  useLayoutEffect(() => () => close(), []);
  useLayoutEffect(() => {
    const element = video.current;
    if (element) element.srcObject = stream;
    return () => { if (element) element.srcObject = null; };
  }, [stream]);

  function start() {
    if (busy.current || room.current || !previewSupported()) return;
    busy.current = true;
    const mine = epoch.current + 1; epoch.current = mine;
    const live = () => epoch.current === mine && room.current === instance;
    const finish = (next: Status) => { if (!live()) return; close(); setStream(null); setStatus(next); };
    const instance: MediaRoom = new MediaRoom(true, noSend, value => { if (live()) setStream(value); }, () => finish('ENDED'), () => finish('ENDED'));
    room.current = instance;
    // Must stay before any await: getDisplayMedia is reached synchronously inside this click.
    const pending = instance.chooseScreen();
    setStatus('CHOOSING');
    pending.then(() => { if (live()) setStatus('PREVIEW'); }, () => finish('DENIED'))
      .finally(() => { busy.current = false; });
  }
  function stop() {
    if (!room.current) return;
    close(); setStream(null); setStatus('STOPPED');
  }

  const active = status === 'CHOOSING' || status === 'PREVIEW';
  return <>
    {!supported && <p role="status">이 브라우저에서는 로컬 화면 미리보기를 지원하지 않습니다. 모바일 기기는 지원하지 않으며, 보안 연결(HTTPS)의 데스크톱 브라우저가 필요합니다.</p>}
    {messages[status] && <p role={status === 'DENIED' ? 'alert' : 'status'}>{messages[status]}</p>}
    <button type="button" onClick={start} disabled={!supported || active}>화면 선택 · 로컬 미리보기 시작</button>
    <button type="button" onClick={stop} disabled={!active}>로컬 미리보기 중지</button>
    <video ref={video} data-testid="local-preview" autoPlay muted playsInline hidden={!stream} aria-label="로컬 화면 미리보기 영상" />
  </>;
}
