// FR-OPP-001(read)/003/004 · /app/opportunities. Every state comes from the server; there is no
// local mock. Until root mounts API-OPP with auth and DB, requests fail and the error state shows.
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { ApiError } from '../../lib/api';
import * as api from './api';
import {
  KIND_LABEL,
  SELF_REPORT_NOTICE,
  STATUS_LABEL,
  SUBMISSION_GUIDE,
  formatDateTime,
  nextStatuses,
} from './status';
import type {
  CheckItem,
  OpportunityDetail,
  OpportunityFilter,
  OpportunityKind,
  OpportunitySummary,
  SavedOpportunity,
} from './types';

type Load<T> =
  | { state: 'loading' }
  | { state: 'error'; message: string; requestId?: string }
  | { state: 'ready'; data: T };

function describeError(error: unknown): { message: string; requestId?: string } {
  if (error instanceof ApiError) {
    const requestId = error.requestId;
    // The shared client reports transport failures as status 0 (NETWORK/CANCELLED timeout).
    if (error.status === 0 && (error.code === 'NETWORK' || error.code === 'CANCELLED'))
      return { message: '서버에 연결할 수 없습니다. 네트워크 상태를 확인하세요.' };
    if (error.status === 503) return { message: '서버 연결 준비 중입니다. 아직 이용할 수 없습니다.', requestId };
    if (error.status === 401) return { message: '로그인이 필요합니다.', requestId };
    if (error.status === 404) return { message: '찾을 수 없거나 접근할 수 없는 항목입니다.', requestId };
    if (error.status === 409)
      return { message: '현재 상태와 충돌합니다. 최신 내용을 다시 불러왔습니다.', requestId };
    if (error.status === 400) return { message: '입력값을 확인하세요.', requestId };
    return { message: '요청을 처리하지 못했습니다. 잠시 후 다시 시도하세요.', requestId };
  }
  return { message: '서버에 연결할 수 없습니다. 네트워크 상태를 확인하세요.' };
}

function ErrorBox({ message, requestId, onRetry }: { message: string; requestId?: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
      <p>{message}</p>
      {requestId && <p className="mt-1 text-xs text-red-600">요청 ID: {requestId}</p>}
      {onRetry && (
        <button type="button" onClick={onRetry} className="mt-2 rounded border border-red-300 px-2 py-1 text-xs">
          다시 시도
        </button>
      )}
    </div>
  );
}

function SourceBadges({ item }: { item: OpportunitySummary }) {
  return (
    <span className="flex flex-wrap gap-1 text-xs">
      <span className="rounded bg-slate-100 px-1.5 py-0.5">{KIND_LABEL[item.kind]}</span>
      {item.source_kind === 'DEMO' && <span className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-800">DEMO 가상 공고</span>}
      {item.needs_verification && <span className="rounded bg-orange-100 px-1.5 py-0.5 text-orange-800">원문 확인 필요</span>}
      {item.deadline_passed && <span className="rounded bg-slate-200 px-1.5 py-0.5">마감</span>}
    </span>
  );
}

function Detail({ id, saved, onSave }: { id: string; saved: boolean; onSave: (id: string) => void }) {
  const [detail, setDetail] = useState<Load<OpportunityDetail>>({ state: 'loading' });
  const load = useCallback(() => {
    setDetail({ state: 'loading' });
    api.getOpportunity(id).then(
      (data) => setDetail({ state: 'ready', data }),
      (error) => setDetail({ state: 'error', ...describeError(error) }),
    );
  }, [id]);
  useEffect(load, [load]);

  if (detail.state === 'loading') return <p className="text-sm text-slate-500" aria-busy="true">공고를 불러오는 중…</p>;
  if (detail.state === 'error') return <ErrorBox message={detail.message} requestId={detail.requestId} onRetry={load} />;
  const d = detail.data;
  return (
    <article className="space-y-3 rounded-lg border border-slate-200 p-4">
      <SourceBadges item={d} />
      <h3 className="text-lg font-semibold">{d.title}</h3>
      <p className="text-sm text-slate-600">{d.organization} · 마감 {formatDateTime(d.deadline_at)}</p>
      <p className="whitespace-pre-wrap text-sm">{d.eligibility}</p>
      <div className="rounded-md bg-sky-50 p-3 text-sm text-sky-900">
        <p>{SUBMISSION_GUIDE[d.submission_mode]}</p>
        <p className="mt-1">제출처: {d.destination ?? '제출처 정보 없음 — 원문을 확인하세요.'}</p>
      </div>
      <div className="text-sm">
        <p className="font-medium">지정 양식</p>
        {d.files.length === 0 ? (
          <p className="text-slate-500">등록된 양식 파일이 없습니다.</p>
        ) : (
          <ul className="list-disc pl-5">
            {d.files.map((file) => (
              <li key={file.filename}>
                {file.original_url ? (
                  <a className="text-sky-700 underline" href={file.original_url} target="_blank" rel="noopener noreferrer">{file.filename}</a>
                ) : (
                  <span>{file.filename} (링크 없음 — 원문 확인 필요)</span>
                )}
              </li>
            ))}
          </ul>
        )}
        {d.original_url ? (
          <a className="mt-1 inline-block text-sky-700 underline" href={d.original_url} target="_blank" rel="noopener noreferrer">원문 공고 열기</a>
        ) : (
          <p className="text-slate-500">원문 링크가 없습니다.</p>
        )}
      </div>
      <button type="button" disabled={saved} onClick={() => onSave(d.id)} className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50">
        {saved ? '내 준비 목록에 있음' : '내 준비 목록에 추가'}
      </button>
    </article>
  );
}

type Run = (action: () => Promise<unknown>) => Promise<boolean>;

// One idempotency key per add intent. A retry of the same text reuses the key and body so the
// server can replay (or 409) instead of creating a duplicate; editing the text starts a new intent.
interface PendingCheck {
  key: string;
  text: string;
  sortOrder: number;
}

// Held by the page (not the card) so typed text and the pending key survive list reloads/errors.
interface CheckDraft {
  text: string;
  pending: PendingCheck | null;
}

type UpdateDraft = (opportunityId: string, update: (draft: CheckDraft) => CheckDraft) => void;

const EMPTY_DRAFT: CheckDraft = { text: '', pending: null };

function Checklist({ saved, run, busy, draft, onDraft }: {
  saved: SavedOpportunity;
  run: Run;
  busy: boolean;
  draft: CheckDraft;
  onDraft: UpdateDraft;
}) {
  const id = saved.opportunity_id;
  const value = draft.text.trim();
  const retrying = draft.pending !== null && draft.pending.text === value;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!value || value.length > 200 || busy) return;
    const intent =
      retrying && draft.pending
        ? draft.pending
        : {
            key: api.newIdempotencyKey(),
            text: value,
            sortOrder: saved.checks.reduce((max, c) => Math.max(max, c.sort_order + 1), 0),
          };
    onDraft(id, (d) => ({ ...d, pending: intent }));
    const ok = await run(() => api.addCheck(id, intent.text, intent.sortOrder, intent.key));
    // On failure the text and key stay so the user can retry the same intent.
    if (ok) onDraft(id, (d) => (d.text.trim() === intent.text ? EMPTY_DRAFT : { ...d, pending: null }));
  };
  const toggle = (check: CheckItem) =>
    void run(() => api.updateCheck(id, check, { completed: !check.completed_at }));
  return (
    <div className="mt-2 space-y-1 text-sm">
      {saved.checks.length === 0 && <p className="text-slate-500">준비 항목이 없습니다.</p>}
      <ul className="space-y-1">
        {saved.checks.map((check) => (
          <li key={check.id} className="flex items-center gap-2">
            <input type="checkbox" checked={Boolean(check.completed_at)} onChange={() => toggle(check)} aria-label={`${check.text} 완료 여부`} />
            <span className={check.completed_at ? 'line-through text-slate-400' : ''}>{check.text}</span>
            <button type="button" onClick={() => void run(() => api.deleteCheck(id, check))} className="ml-auto text-xs text-red-700">삭제</button>
          </li>
        ))}
      </ul>
      <form onSubmit={(e) => void submit(e)} className="flex gap-2">
        <input value={draft.text} onChange={(e) => { const text = e.target.value; onDraft(id, (d) => ({ ...d, text })); }} maxLength={200} placeholder="준비 항목 추가" aria-label="준비 항목" className="flex-1 rounded border border-slate-300 px-2 py-1" />
        <button type="submit" disabled={busy} className="rounded border border-slate-300 px-2 py-1 disabled:opacity-50">
          {retrying ? '다시 시도' : '추가'}
        </button>
      </form>
    </div>
  );
}

function SavedCard({ saved, run, busy, draft, onDraft }: {
  saved: SavedOpportunity;
  run: Run;
  busy: boolean;
  draft: CheckDraft;
  onDraft: UpdateDraft;
}) {
  const mode = saved.opportunity?.submission_mode;
  return (
    <li className="rounded-lg border border-slate-200 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{saved.opportunity?.title ?? '더 이상 공개되지 않는 공고'}</span>
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{STATUS_LABEL[saved.status]}</span>
      </div>
      {saved.status === 'self_reported_submitted' && (
        <p className="mt-1 text-xs text-amber-800">
          {formatDateTime(saved.self_reported_submitted_at)}에 기록 · {SELF_REPORT_NOTICE}
        </p>
      )}
      <div className="mt-2 flex flex-wrap gap-1">
        {nextStatuses(saved.status, mode).map((status) => (
          <button key={status} type="button" onClick={() => void run(() => api.updateSaved(saved.opportunity_id, saved.revision, { status }))} className="rounded border border-slate-300 px-2 py-0.5 text-xs">
            {STATUS_LABEL[status]}(으)로 변경
          </button>
        ))}
        <button type="button" onClick={() => void run(() => api.deleteSaved(saved.opportunity_id, saved.revision))} className="rounded border border-red-300 px-2 py-0.5 text-xs text-red-700">
          목록에서 삭제
        </button>
      </div>
      <Checklist saved={saved} run={run} busy={busy} draft={draft} onDraft={onDraft} />
    </li>
  );
}

export default function OpportunitiesPage() {
  const [filter, setFilter] = useState<OpportunityFilter>({ openOnly: true });
  const [list, setList] = useState<Load<OpportunitySummary[]>>({ state: 'loading' });
  const [saved, setSaved] = useState<Load<SavedOpportunity[]>>({ state: 'loading' });
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ ok: boolean; message: string; requestId?: string } | null>(null);
  const [drafts, setDrafts] = useState<Record<string, CheckDraft>>({});
  const updateDraft = useCallback<UpdateDraft>(
    (id, update) => setDrafts((all) => ({ ...all, [id]: update(all[id] ?? EMPTY_DRAFT) })),
    [],
  );

  const loadList = useCallback(() => {
    setList({ state: 'loading' });
    api.listOpportunities(filter).then(
      (page) => setList({ state: 'ready', data: page.items }),
      (error) => setList({ state: 'error', ...describeError(error) }),
    );
  }, [filter]);

  const loadSaved = useCallback(() => {
    setSaved({ state: 'loading' });
    return api.listSaved().then(
      (data) => setSaved({ state: 'ready', data: data.items }),
      (error) => setSaved({ state: 'error', ...describeError(error) }),
    );
  }, []);

  useEffect(loadList, [loadList]);
  useEffect(() => void loadSaved(), [loadSaved]);

  // Mutations never update UI optimistically: the list is re-read from the server afterwards.
  // Resolves true only when the server accepted the mutation.
  const run = useCallback<Run>(
    async (action) => {
      setBusy(true);
      setNotice(null);
      let ok = false;
      try {
        await action();
        ok = true;
        setNotice({ ok: true, message: '서버가 요청을 처리했습니다. 아래 목록은 서버에서 다시 불러온 내용입니다.' });
      } catch (error) {
        setNotice({ ok: false, ...describeError(error) });
      }
      await loadSaved();
      setBusy(false);
      return ok;
    },
    [loadSaved],
  );

  const savedIds = new Set(saved.state === 'ready' ? saved.data.map((s) => s.opportunity_id) : []);

  return (
    <main className="mx-auto grid max-w-6xl gap-6 p-4 lg:grid-cols-[1fr_1fr]">
      <section aria-labelledby="opp-list" className="space-y-3">
        <h2 id="opp-list" className="text-xl font-semibold">장학금·공모전·기회</h2>
        <form className="flex flex-wrap gap-2 text-sm" onSubmit={(e) => { e.preventDefault(); loadList(); }}>
          <select aria-label="분류" value={filter.kind ?? ''} onChange={(e) => setFilter({ ...filter, kind: (e.target.value || undefined) as OpportunityKind | undefined })} className="rounded border border-slate-300 px-2 py-1">
            <option value="">전체 분류</option>
            {Object.entries(KIND_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <input aria-label="검색어" maxLength={50} value={filter.q ?? ''} onChange={(e) => setFilter({ ...filter, q: e.target.value })} placeholder="제목·주관 기관" className="rounded border border-slate-300 px-2 py-1" />
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={Boolean(filter.openOnly)} onChange={(e) => setFilter({ ...filter, openOnly: e.target.checked })} />
            마감 전만
          </label>
        </form>
        {list.state === 'loading' && <p className="text-sm text-slate-500" aria-busy="true">목록을 불러오는 중…</p>}
        {list.state === 'error' && <ErrorBox message={list.message} requestId={list.requestId} onRetry={loadList} />}
        {list.state === 'ready' && list.data.length === 0 && <p className="text-sm text-slate-500">조건에 맞는 공고가 없습니다.</p>}
        {list.state === 'ready' && list.data.length > 0 && (
          <ul className="space-y-2">
            {list.data.map((item) => (
              <li key={item.id}>
                <button type="button" onClick={() => setSelected(item.id)} className={`w-full rounded-lg border p-3 text-left ${selected === item.id ? 'border-sky-500' : 'border-slate-200'}`}>
                  <SourceBadges item={item} />
                  <span className="mt-1 block font-medium">{item.title}</span>
                  <span className="block text-xs text-slate-600">{item.organization} · 마감 {formatDateTime(item.deadline_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {selected && <Detail id={selected} saved={savedIds.has(selected)} onSave={(id) => void run(() => api.saveOpportunity(id))} />}
      </section>

      <section aria-labelledby="opp-saved" className="space-y-3" aria-busy={busy}>
        <h2 id="opp-saved" className="text-xl font-semibold">내 준비 목록</h2>
        <p className="text-xs text-slate-500">본인만 볼 수 있습니다. 외부 기관 제출은 이 화면에서 처리되지 않습니다.</p>
        {notice && (notice.ok ? <p role="status" className="text-sm text-slate-700">{notice.message}</p> : <ErrorBox message={notice.message} requestId={notice.requestId} />)}
        {saved.state === 'loading' && <p className="text-sm text-slate-500" aria-busy="true">내 준비 목록을 불러오는 중…</p>}
        {saved.state === 'error' && <ErrorBox message={saved.message} requestId={saved.requestId} onRetry={() => void loadSaved()} />}
        {saved.state === 'ready' && saved.data.length === 0 && <p className="text-sm text-slate-500">아직 담아 둔 공고가 없습니다.</p>}
        {saved.state === 'ready' && saved.data.length > 0 && (
          <ul className="space-y-3">
            {saved.data.map((item) => (
              <SavedCard key={item.opportunity_id} saved={item} run={run} busy={busy} draft={drafts[item.opportunity_id] ?? EMPTY_DRAFT} onDraft={updateDraft} />
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
