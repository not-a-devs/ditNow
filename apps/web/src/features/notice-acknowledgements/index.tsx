import { useLayoutEffect, useRef, useState } from 'react';
import { ApiError } from '../../lib/api';
import {
  UUID_PATTERN, fetchOwnState, fetchSummary, newIntentKey, sendAck, sendAckRequest,
  type AckSummary, type OwnState,
} from './api';

interface Props { sessionGeneration: number; initialNoticeId?: string }
interface Intent { kind: 'request' | 'ack'; noticeId: string; revision: number | null; key: string }

// Dormant FR-NOT-004 screen: not routed. The parent remounts it per session generation.
export default function NoticeAcknowledgementsPage({ sessionGeneration, initialNoticeId = '' }: Props) {
  return <Workspace key={sessionGeneration} initialNoticeId={initialNoticeId} />;
}

function Workspace({ initialNoticeId }: { initialNoticeId: string }) {
  const [input, setInput] = useState(initialNoticeId);
  const [noticeId, setNoticeId] = useState<string | null>(null);
  const [own, setOwn] = useState<OwnState | null>(null);
  const [summary, setSummary] = useState<AckSummary | null>(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [denied, setDenied] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const busyRef = useRef(false);
  const epochRef = useRef(0);
  const aliveRef = useRef(false);
  const controllerRef = useRef<AbortController | null>(null);
  const intentRef = useRef<Intent | null>(null);

  useLayoutEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
      epochRef.current += 1;
      controllerRef.current?.abort();
      controllerRef.current = null;
      busyRef.current = false;
      intentRef.current = null;
    };
  }, []);

  const isCurrent = (epoch: number) => aliveRef.current && epoch === epochRef.current;

  function invalidate() {
    epochRef.current += 1;
    controllerRef.current?.abort();
    controllerRef.current = null;
    busyRef.current = false;
    setBusy(false);
  }

  function clearPrivate() {
    intentRef.current = null;
    setOwn(null); setSummary(null); setConsent(false); setNotice(''); setError('');
  }

  function begin() {
    if (busyRef.current || denied) return null;
    busyRef.current = true;
    setBusy(true);
    setError(''); setNotice('');
    const controller = new AbortController();
    controllerRef.current = controller;
    return { epoch: epochRef.current, signal: controller.signal };
  }

  function finish(epoch: number) {
    if (!isCurrent(epoch)) return;
    busyRef.current = false;
    controllerRef.current = null;
    setBusy(false);
  }

  function fail(caught: unknown, epoch: number) {
    if (!isCurrent(epoch)) return;
    const status = caught instanceof ApiError ? caught.status : 0;
    if (status === 401 || status === 403) {
      invalidate();
      clearPrivate();
      setNoticeId(null);
      setDenied(true);
      return;
    }
    const ambiguous = status === 0 || status >= 500;
    if (!ambiguous) intentRef.current = null;
    setError(ambiguous && intentRef.current
      ? '결과를 확인하지 못했습니다. 다시 시도하면 같은 요청으로 한 번만 처리됩니다.'
      : caught instanceof ApiError ? caught.message : '요청을 처리하지 못했습니다.');
  }

  async function refresh(id: string, epoch: number, signal: AbortSignal) {
    const fresh = await fetchOwnState(id, signal);
    if (!isCurrent(epoch)) return null;
    setOwn(fresh);
    if (!fresh.can_view_summary) { setSummary(null); return fresh; }
    const counts = await fetchSummary(id, signal);
    if (!isCurrent(epoch)) return null;
    setSummary(counts);
    return fresh;
  }

  async function lookup() {
    const id = input.trim().toLowerCase();
    if (!UUID_PATTERN.test(id) || busyRef.current || denied) {
      if (!UUID_PATTERN.test(id)) setError('공지 참조 형식을 확인해 주세요.');
      return;
    }
    invalidate();
    clearPrivate();
    setNoticeId(id);
    const run = begin();
    if (!run) return;
    try { await refresh(id, run.epoch, run.signal); } catch (caught) { fail(caught, run.epoch); } finally { finish(run.epoch); }
  }

  // A key is reused only for the identical body: same kind, notice and (for ack) request revision.
  function intentFor(kind: Intent['kind'], id: string, revision: number | null = null) {
    const prior = intentRef.current;
    if (prior && prior.kind === kind && prior.noticeId === id && prior.revision === revision) return prior.key;
    intentRef.current = { kind, noticeId: id, revision, key: newIntentKey() };
    return intentRef.current.key;
  }

  async function submitRequest() {
    if (!noticeId || !own?.can_request || !consent) return;
    const run = begin();
    if (!run) return;
    const id = noticeId;
    try {
      const receipt = await sendAckRequest(id, intentFor('request', id), run.signal);
      if (!isCurrent(run.epoch)) return;
      const fresh = await refresh(id, run.epoch, run.signal);
      if (!fresh || !isCurrent(run.epoch)) return;
      intentRef.current = null;
      setConsent(false);
      if (fresh.requested && fresh.request_revision === receipt.request_revision) setNotice('확인 요청이 등록된 것을 다시 조회로 확인했습니다. (가상 DEMO·공식 효력 없음)');
      else setError('요청 결과가 현재 상태와 일치하지 않습니다. 다시 조회해 주세요.');
    } catch (caught) { fail(caught, run.epoch); } finally { finish(run.epoch); }
  }

  async function submitAck() {
    if (!noticeId || !own?.can_acknowledge || own.request_revision === null || !consent) return;
    const revision = own.request_revision;
    const run = begin();
    if (!run) return;
    const id = noticeId;
    try {
      const receipt = await sendAck(id, revision, intentFor('ack', id, revision), run.signal);
      if (!isCurrent(run.epoch)) return;
      const fresh = await refresh(id, run.epoch, run.signal);
      if (!fresh || !isCurrent(run.epoch)) return;
      intentRef.current = null;
      setConsent(false);
      if (fresh.acknowledged && fresh.request_revision === receipt.request_revision && fresh.acknowledged_at === receipt.acknowledged_at) setNotice('본인 확인 기록을 다시 조회로 확인했습니다. (가상 DEMO·공식 효력 없음)');
      else setError('확인 결과가 현재 상태와 일치하지 않습니다. 다시 조회해 주세요.');
    } catch (caught) { fail(caught, run.epoch); } finally { finish(run.epoch); }
  }

  function changeInput(value: string) {
    invalidate();
    clearPrivate();
    setNoticeId(null);
    setInput(value);
  }

  const disabled = busy || denied;
  return (
    <section aria-labelledby="notice-ack-title">
      <h1 id="notice-ack-title">공지 확인 요청</h1>
      <p>가상 DEMO 기능입니다. 서버 메모리에만 있고 재시작하면 초기화되며 공식 효력이 없습니다.</p>
      {denied && <p role="alert">권한이 확인되지 않아 개인 정보를 지웠습니다. 다시 로그인하면 사용할 수 있습니다.</p>}
      <label>
        공지 참조
        <input value={input} disabled={denied} onChange={event => changeInput(event.target.value)} />
      </label>
      <button type="button" disabled={disabled} onClick={() => void lookup()}>상태 조회</button>
      {error && !denied && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {own && (
        <div>
          <p>{own.requested ? '확인 요청이 열려 있습니다.' : '확인 요청이 없습니다.'}</p>
          {own.acknowledged && <p>본인 확인 완료</p>}
          {(own.can_request || own.can_acknowledge) && (
            <label>
              <input type="checkbox" checked={consent} disabled={disabled} onChange={event => setConsent(event.target.checked)} />
              {own.can_request ? '이 공지에 확인 요청을 만드는 데 동의합니다' : '이 공지를 확인했음을 기록하는 데 동의합니다'}
            </label>
          )}
          {own.can_request && <button type="button" disabled={disabled || !consent} onClick={() => void submitRequest()}>확인 요청 만들기</button>}
          {own.can_acknowledge && <button type="button" disabled={disabled || !consent} onClick={() => void submitAck()}>확인 기록</button>}
        </div>
      )}
      {summary && <p>현재 대상 {summary.eligible_total}명 중 {summary.acknowledged_count}명 확인 (개인 식별 정보 없음)</p>}
    </section>
  );
}
