import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import {
  ambiguous, authFailure, CATEGORY_LABELS, CLASSIFICATION_LABELS, conflict, listQueue, NOTE_LABELS, patchItem, readItem,
  RESOLUTION_LABELS, sameItem, STATUS_LABELS,
  type Category, type Classification, type Filters, type Item, type NoteCode, type Page, type Patch, type Resolution, type Status,
} from './api';

const DISCLAIMER = '이 화면은 가상(DEMO) 시연용 감사 큐입니다. 서버 프로세스 메모리(PROCESS_MEMORY)에만 저장되고 재시작하면 초기화되며, 실제 공지·게시물·신고나 작성자 정보는 포함하지 않고 어떠한 공식 효력이나 실제 제재도 발생하지 않습니다.';
const safeError = '감사 큐를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.';

// sessionGeneration comes from the shared auth shell when integrated; a denial blocks the
// workspace until that verified generation changes. There is no local reset.
export default function AdminAuditQueuePage({ sessionGeneration = 0 }: { sessionGeneration?: number }) {
  const [deniedGeneration, setDeniedGeneration] = useState<number | null>(null);
  const onDenied = useCallback(() => setDeniedGeneration(sessionGeneration), [sessionGeneration]);
  return <section aria-labelledby="admin-audit-title"><h1 id="admin-audit-title">운영 감사 큐 (시연)</h1>
    <p role="note">{DISCLAIMER}</p>
    {deniedGeneration === sessionGeneration
      ? <div role="alert"><p>현재 검토 권한을 확인하지 못해 화면의 내용을 모두 비웠습니다. 다시 로그인해 세션이 갱신되기 전까지 비활성화됩니다.</p></div>
      : <Workspace key={sessionGeneration} onDenied={onDenied} />}
  </section>;
}

type Draft = { classification: Classification | ''; resolution: Resolution | ''; note: NoteCode | '' };
const emptyDraft: Draft = { classification: '', resolution: '', note: '' };

function Workspace({ onDenied }: { onDenied: () => void }) {
  const epoch = useRef(0);
  const controllers = useRef(new Set<AbortController>());
  const busy = useRef(false);
  const intent = useRef<{ signature: string; key: string } | null>(null);
  const [filters, setFilters] = useState<Filters>({ status: '', category: '' });
  const [page, setPage] = useState<Page | null>(null);
  const [listState, setListState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [reloadTick, setReloadTick] = useState(0);
  const [selected, setSelected] = useState<Item | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [consent, setConsent] = useState(false);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // Unmount (generation change or denial) invalidates every in-flight await synchronously.
  useLayoutEffect(() => {
    const owned = controllers.current;
    return () => { epoch.current += 1; busy.current = false; for (const c of owned) c.abort(); owned.clear(); };
  }, []);

  const begin = useCallback(() => {
    const controller = new AbortController();
    controllers.current.add(controller);
    const at = epoch.current;
    const current = () => at === epoch.current && !controller.signal.aborted;
    const done = () => controllers.current.delete(controller);
    return { controller, current, done };
  }, []);

  const deny = useCallback(() => {
    epoch.current += 1; busy.current = false; intent.current = null;
    for (const c of controllers.current) c.abort();
    controllers.current.clear();
    setPage(null); setSelected(null); setDraft(emptyDraft); setConsent(false); setMessage(null);
    onDenied();
  }, [onDenied]);

  const listSeq = useRef(0);
  useEffect(() => {
    const seq = ++listSeq.current;
    const { controller, current, done } = begin();
    setListState('loading');
    listQueue(filters, controller.signal).then(result => {
      if (!current() || seq !== listSeq.current) return;
      setPage(result); setListState('ready');
    }, failure => {
      if (!current() || seq !== listSeq.current) return;
      if (authFailure(failure)) { deny(); return; }
      setPage(null); setListState('error');
    }).finally(done);
    return () => controller.abort();
  }, [filters, reloadTick, begin, deny]);

  const detailSeq = useRef(0);
  async function open(id: string) {
    if (busy.current) return;
    const seq = ++detailSeq.current;
    const { controller, current, done } = begin();
    setMessage(null); setConsent(false); setDraft(emptyDraft); intent.current = null;
    try {
      const item = await readItem(id, controller.signal);
      if (!current() || seq !== detailSeq.current) return;
      setSelected(item);
    } catch (failure) {
      if (!current() || seq !== detailSeq.current) return;
      if (authFailure(failure)) { deny(); return; }
      setSelected(null); setMessage('항목을 불러오지 못했습니다. 목록을 새로 확인해 주세요.');
    } finally { done(); }
  }

  function buildPatch(item: Item): Patch | null {
    if (!draft.note) return null;
    if (item.status === 'PENDING' && draft.classification) return { revision: item.revision, classification: draft.classification, note_code: draft.note };
    if (item.status === 'CLASSIFIED' && draft.resolution) return { revision: item.revision, resolution: draft.resolution, note_code: draft.note };
    return null;
  }

  async function submit(item: Item) {
    const body = buildPatch(item);
    if (busy.current || !consent || !body) return;
    busy.current = true;
    const { controller, current, done } = begin();
    // Reuse the idempotency key only for the identical intent (manual retry after an ambiguous result).
    const signature = JSON.stringify([item.id, body]);
    const reused = intent.current?.signature === signature ? intent.current : null;
    const key = reused?.key ?? globalThis.crypto.randomUUID();
    intent.current = { signature, key };
    setPending(true); setMessage(null); setConsent(false);
    try {
      const receipt = await patchItem(item.id, body, key, controller.signal);
      if (!current()) return;
      const fresh = await readItem(item.id, controller.signal);
      if (!current()) return;
      intent.current = null;
      setSelected(fresh); setDraft(emptyDraft);
      setMessage(sameItem(receipt, fresh)
        ? `시연 처리 기록이 서버 재조회로 확인되었습니다(revision ${fresh.revision}). 공식 효력은 없습니다.`
        : '처리 결과가 재조회 결과와 일치하지 않습니다. 최신 상태를 확인해 주세요.');
      setReloadTick(t => t + 1);
    } catch (failure) {
      if (!current()) return;
      if (authFailure(failure)) { deny(); return; }
      if (conflict(failure)) {
        intent.current = null;
        setMessage('다른 변경과 충돌했거나 이미 처리된 항목입니다. 최신 상태를 다시 불러옵니다.');
        setReloadTick(t => t + 1);
        busy.current = false; setPending(false); done();
        await open(item.id);
        return;
      }
      if (!ambiguous(failure)) intent.current = null;
      setMessage(ambiguous(failure)
        ? '처리 결과를 확인하지 못했습니다. 자동으로 다시 보내지 않았습니다. 최신 상태를 확인한 뒤 필요하면 다시 시도해 주세요.'
        : '입력값을 확인해 주세요.');
    } finally {
      if (current()) { busy.current = false; setPending(false); }
      done();
    }
  }

  const items = page?.items ?? [];
  return <>
    <fieldset aria-label="필터"><legend>필터</legend>
      <label>상태 <select value={filters.status} disabled={pending} onChange={e => setFilters(f => ({ ...f, status: e.target.value as Status | '' }))}>
        <option value="">전체</option>{(Object.keys(STATUS_LABELS) as Status[]).map(s => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
      </select></label>
      <label>분류 <select value={filters.category} disabled={pending} onChange={e => setFilters(f => ({ ...f, category: e.target.value as Category | '' }))}>
        <option value="">전체</option>{(Object.keys(CATEGORY_LABELS) as Category[]).map(c => <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>)}
      </select></label>
    </fieldset>
    {listState === 'loading' && <p role="status">감사 큐를 불러오는 중입니다.</p>}
    {listState === 'error' && <div role="alert"><p>{safeError}</p><button onClick={() => setReloadTick(t => t + 1)}>목록 다시 시도</button></div>}
    {listState === 'ready' && items.length === 0 && <p>조건에 맞는 시연 항목이 없습니다.</p>}
    {items.length > 0 && <ul aria-label="감사 큐 목록">{items.map(i => <li key={i.id}>
      {i.demo_label} · {CATEGORY_LABELS[i.category]} · {STATUS_LABELS[i.status]}
      <button disabled={pending} onClick={() => void open(i.id)} aria-label={`${i.demo_label} 열기`}>열기</button>
    </li>)}</ul>}
    {message && <p role="alert">{message}</p>}
    {selected && <section aria-label="선택한 항목"><h2>{selected.demo_label}</h2>
      <p>{CATEGORY_LABELS[selected.category]} · {STATUS_LABELS[selected.status]} · revision {selected.revision}</p>
      {selected.classification && <p>분류: {CLASSIFICATION_LABELS[selected.classification]}</p>}
      {selected.resolution && <p>처리: {RESOLUTION_LABELS[selected.resolution]}</p>}
      {selected.note_code && <p>메모 코드: {NOTE_LABELS[selected.note_code]}</p>}
      {selected.status === 'RESOLVED' ? <p>처리 확정된 시연 항목은 변경할 수 없습니다.</p> : <form onSubmit={e => { e.preventDefault(); void submit(selected); }}>
        {selected.status === 'PENDING' && <label>분류 선택 <select value={draft.classification} onChange={e => setDraft(d => ({ ...d, classification: e.target.value as Classification | '' }))}>
          <option value="">선택</option>{(Object.keys(CLASSIFICATION_LABELS) as Classification[]).map(c => <option key={c} value={c}>{CLASSIFICATION_LABELS[c]}</option>)}
        </select></label>}
        {selected.status === 'CLASSIFIED' && <label>처리 선택 <select value={draft.resolution} onChange={e => setDraft(d => ({ ...d, resolution: e.target.value as Resolution | '' }))}>
          <option value="">선택</option>{(Object.keys(RESOLUTION_LABELS) as Resolution[]).map(r => <option key={r} value={r}>{RESOLUTION_LABELS[r]}</option>)}
        </select></label>}
        <label>메모 코드 <select value={draft.note} onChange={e => setDraft(d => ({ ...d, note: e.target.value as NoteCode | '' }))}>
          <option value="">선택</option>{(Object.keys(NOTE_LABELS) as NoteCode[]).map(n => <option key={n} value={n}>{NOTE_LABELS[n]}</option>)}
        </select></label>
        <label><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} /> 가상 시연 기록이며 실제 제재·공식 효력이 없음을 확인하고 저장합니다.</label>
        <button type="submit" disabled={pending || !consent || !buildPatch(selected)}>{pending ? '저장 중' : '시연 처리 저장'}</button>
      </form>}
    </section>}
  </>;
}
