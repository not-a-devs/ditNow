// FR-OPP-002 personalized discovery + rule-based FR-AI-002/003 subset. Everything shown comes from
// the server; there is no local mock or AI call. Until root mounts the router with auth, academic
// context and catalog providers, requests fail with 503 and the error state is shown.
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '../../lib/api';
import { KIND_LABEL, formatDateTime } from '../opportunities/status';
import type { OpportunityKind } from '../opportunities/types';
import * as api from './api';
import PreparationDraft from './PreparationDraft';
import {
  CAUTION_LABEL,
  FRESHNESS_LABEL,
  REASON_LABEL,
  STEP_LABEL,
  STEP_MISSING,
  WINDOW_LABEL,
} from './labels';
import type { ContextBasis, MatchFilter, MatchItem, MatchPage, MatchReason, OpportunityBrief, RecruitmentRefs } from './types';

const PAGE_SIZE = 10;
const DISCLAIMER = '서버 고정 규칙으로 정렬한 참고 목록입니다. AI 생성 결과가 아니며 지원 자격을 보장하지 않습니다.';
const TOUCH_TARGET = { minHeight: 24 };

interface Described {
  message: string;
  requestId?: string;
  conflict?: boolean;
}

function describeError(error: unknown): Described {
  if (error instanceof ApiError) {
    const requestId = error.requestId;
    if (error.status === 0) return { message: '서버에 연결할 수 없습니다. 네트워크 상태를 확인하세요.' };
    if (error.status === 503) return { message: '서버 연결 준비 중입니다. 아직 이용할 수 없습니다.', requestId };
    if (error.status === 401) return { message: '로그인이 필요합니다.', requestId };
    if (error.status === 403)
      return { message: '현재 학적 소속이 확인되지 않아 맞춤 공고를 볼 수 없습니다.', requestId };
    if (error.status === 404) return { message: '찾을 수 없거나 더 이상 공개되지 않은 공고입니다.', requestId };
    if (error.status === 409)
      return { message: '그 사이 결과가 바뀌었습니다. 처음부터 다시 불러오세요.', requestId, conflict: true };
    if (error.status === 400) return { message: '입력값을 확인하세요.', requestId };
    return { message: '요청을 처리하지 못했습니다. 잠시 후 다시 시도하세요.', requestId };
  }
  return { message: '서버에 연결할 수 없습니다. 네트워크 상태를 확인하세요.' };
}

/** Aborts the previous request held in `ref` and returns the signal for its replacement. */
function restart(ref: { current: AbortController | null }): AbortSignal {
  ref.current?.abort();
  ref.current = new AbortController();
  return ref.current.signal;
}

type ListState =
  | { state: 'loading' }
  | ({ state: 'error' } & Described)
  | { state: 'ready'; page: MatchPage; items: MatchItem[] };

type BriefState =
  | { id: string; state: 'loading' }
  | ({ id: string; state: 'error' } & Described)
  | { id: string; state: 'ready'; data: OpportunityBrief };

function ErrorBox({ message, requestId, onRetry, retryLabel = '다시 시도' }: Described & { onRetry?: () => void; retryLabel?: string }) {
  return (
    <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
      <p>{message}</p>
      {requestId && <p className="mt-1 text-xs text-red-600">요청 ID: {requestId}</p>}
      {onRetry && (
        <button type="button" onClick={onRetry} style={TOUCH_TARGET} className="mt-2 rounded border border-red-300 px-2 py-1 text-xs">
          {retryLabel}
        </button>
      )}
    </div>
  );
}

function ExternalLink({ href, children }: { href: string | null | undefined; children: string }) {
  const safe = api.safeHref(href);
  if (!safe) return null;
  return (
    <a className="text-sky-700 underline" href={safe} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}

function reasonText(reason: MatchReason): string {
  const value = reason.code === 'KIND_INTEREST' && reason.value
    ? KIND_LABEL[reason.value as OpportunityKind] ?? reason.value
    : reason.value;
  return value ? `${REASON_LABEL[reason.code]} (${value})` : REASON_LABEL[reason.code];
}

function Reasons({ reasons }: { reasons: MatchReason[] }) {
  if (reasons.length === 0) return <p className="text-xs text-slate-500">일치한 규칙 없음</p>;
  return (
    <ul aria-label="일치 근거" className="list-disc pl-5 text-xs text-slate-700">
      {reasons.map((reason, index) => (
        <li key={`${reason.code}-${index}`}>
          {reasonText(reason)} <span className="text-slate-400">· 근거 필드 {reason.source_field}</span>
        </li>
      ))}
    </ul>
  );
}

function Recruitment({ refs }: { refs: RecruitmentRefs }) {
  if (refs.status === 'NOT_CONNECTED')
    return <p className="text-xs text-slate-500">팀원 모집 정보는 커뮤니티 이용이 확인되고 연결된 경우에만 표시됩니다.</p>;
  if (refs.status === 'UNAVAILABLE') return <p className="text-xs text-slate-500">팀원 모집 정보를 불러오지 못했습니다.</p>;
  if (refs.open_count === 0) return <p className="text-xs text-slate-500">연결된 모집 중 팀원 모집 없음</p>;
  return (
    <div className="text-xs text-slate-700">
      <p>연결된 모집 중 팀원 모집 {refs.open_count}건</p>
      <ul className="list-disc pl-5">
        {refs.items.map((ref) => (
          <li key={ref.id}>
            {ref.title} · {ref.field} · 마감 {formatDateTime(ref.deadline_at)}
            {ref.matched_keywords.length > 0 && ` · 관심 키워드: ${ref.matched_keywords.join(', ')}`}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ContextLine({ context }: { context: ContextBasis }) {
  const memberships = context.memberships.length
    ? context.memberships.map((m) => (m.grade ? `${m.department_code} ${m.grade}학년` : m.department_code)).join(', ')
    : '확인된 학과·학년 소속 없음(전교 공고만 해당)';
  return <p className="text-xs text-slate-600">현재 소속 기준: {memberships}</p>;
}

function MatchCard({ item, onBrief }: { item: MatchItem; onBrief: (id: string) => void }) {
  const o = item.opportunity;
  return (
    <li style={{ minWidth: 0 }} className="space-y-1 rounded-md border border-slate-200 p-3">
      <p className="text-xs text-slate-500">
        {KIND_LABEL[o.kind]} · {o.organization.trim() || '미확인'}
        {o.source_kind === 'DEMO' && <span className="ml-1 rounded bg-amber-100 px-1 text-amber-800">DEMO 가상 공고</span>}
      </p>
      <h3 className="font-medium">{o.title}</h3>
      <p className="text-xs">
        {WINDOW_LABEL[item.window]} · 마감 {formatDateTime(o.deadline_at)}
      </p>
      <p className={`text-xs ${item.freshness === 'CURRENT' ? 'text-slate-600' : 'text-amber-700'}`}>
        {FRESHNESS_LABEL[item.freshness]}
        {item.checked_at && ` (확인 ${formatDateTime(item.checked_at)})`}
      </p>
      <Reasons reasons={item.reasons} />
      <p className="text-xs">
        {api.safeHref(item.source_url) ? <ExternalLink href={item.source_url}>원문 보기</ExternalLink> : '원문 링크 없음'}
      </p>
      <Recruitment refs={item.recruitment} />
      <button type="button" onClick={() => onBrief(o.id)} style={TOUCH_TARGET} className="rounded border border-slate-300 px-2 py-1 text-xs">
        요약·절차 보기
      </button>
    </li>
  );
}

function BriefPanel({ brief }: { brief: OpportunityBrief }) {
  const d = brief.opportunity;
  return (
    <article aria-label="공고 요약" style={{ minWidth: 0 }} className="space-y-3 rounded-md border border-slate-200 p-3 text-sm">
      <h3 className="font-semibold">{d.title}</h3>
      <p className="text-xs text-slate-600">{brief.provenance.notice}</p>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
        <dt>주관</dt><dd>{d.organization.trim() || '미확인'}</dd>
        <dt>접수</dt><dd>{formatDateTime(d.apply_starts_at)} ~ {formatDateTime(d.deadline_at)} ({WINDOW_LABEL[brief.window]})</dd>
        <dt>원문 확인</dt><dd>{FRESHNESS_LABEL[brief.freshness]}</dd>
        <dt>대상 범위</dt><dd>{brief.match.in_scope ? '현재 소속이 대상 범위에 포함' : '현재 소속이 대상 범위에 포함되지 않음'}</dd>
      </dl>
      <section>
        <h4 className="text-xs font-semibold">지원 조건 원문</h4>
        <p className="whitespace-pre-wrap text-xs">{d.eligibility}</p>
      </section>
      <Reasons reasons={brief.match.reasons} />
      <section>
        <h4 className="text-xs font-semibold">지원 절차(원문 필드 기반 고정 안내)</h4>
        <ol aria-label="지원 절차" className="list-decimal pl-5 text-xs">
          {brief.procedure.map((step) => (
            <li key={step.order}>
              {STEP_LABEL[step.code]}
              {step.available ? (
                <>
                  {step.evidence_value && ` — ${step.evidence_value}`}{' '}
                  <ExternalLink href={step.evidence_url}>링크</ExternalLink>
                </>
              ) : (
                <span className="text-amber-700"> — {step.evidence_value ? `${step.evidence_value}: ` : ''}{STEP_MISSING[step.code]}</span>
              )}
              <span className="text-slate-400"> · 근거 필드 {step.evidence_field}</span>
            </li>
          ))}
        </ol>
      </section>
      <section>
        <h4 className="text-xs font-semibold">주의</h4>
        <ul aria-label="주의 사항" className="list-disc pl-5 text-xs">
          {brief.cautions.map((caution) => <li key={caution.code}>{CAUTION_LABEL[caution.code]}</li>)}
        </ul>
      </section>
      <Recruitment refs={brief.recruitment} />
    </article>
  );
}

export default function OpportunityMatchingPage({ onSaved }: { onSaved?: () => void } = {}) {
  const [kinds, setKinds] = useState<OpportunityKind[]>([]);
  const [keywordText, setKeywordText] = useState('');
  const [includeClosed, setIncludeClosed] = useState(false);
  const [applied, setApplied] = useState<MatchFilter>({ kinds: [], keywords: [] });
  const [list, setList] = useState<ListState>({ state: 'loading' });
  const [moreError, setMoreError] = useState<Described | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [brief, setBrief] = useState<BriefState | null>(null);
  const [keywordError, setKeywordError] = useState<string | null>(null);
  // Only the latest request may update state; late responses of older requests are ignored.
  // Superseded requests are also aborted so they stop using the network.
  const listSeq = useRef(0);
  const briefSeq = useRef(0);
  const listAbort = useRef<AbortController | null>(null);
  const briefAbort = useRef<AbortController | null>(null);

  const load = useCallback((filter: MatchFilter) => {
    const id = ++listSeq.current;
    briefSeq.current += 1;
    briefAbort.current?.abort();
    const signal = restart(listAbort);
    setList({ state: 'loading' });
    setMoreError(null);
    setLoadingMore(false);
    setBrief(null);
    api.listMatches({ ...filter, limit: PAGE_SIZE }, signal).then(
      (page) => { if (id === listSeq.current) setList({ state: 'ready', page, items: page.items }); },
      (error) => { if (id === listSeq.current) setList({ state: 'error', ...describeError(error) }); },
    );
  }, []);

  useEffect(() => load(applied), [applied, load]);

  // On unmount, end the epoch: no in-flight response may update state, and requests stop.
  useEffect(() => () => {
    listSeq.current += 1;
    briefSeq.current += 1;
    listAbort.current?.abort();
    briefAbort.current?.abort();
  }, []);

  const reload = () => load(applied);

  const loadMore = () => {
    if (list.state !== 'ready' || !list.page.next_cursor) return;
    const id = listSeq.current;
    const previous = list.items;
    const signal = restart(listAbort);
    setLoadingMore(true);
    setMoreError(null);
    api.listMatches({ ...applied, limit: PAGE_SIZE, cursor: list.page.next_cursor }, signal).then(
      (page) => {
        if (id !== listSeq.current) return;
        setList({ state: 'ready', page, items: [...previous, ...page.items] });
        setLoadingMore(false);
      },
      (error) => {
        if (id !== listSeq.current) return;
        setMoreError(describeError(error));
        setLoadingMore(false);
      },
    );
  };

  const openBrief = (opportunityId: string) => {
    const id = ++briefSeq.current;
    const signal = restart(briefAbort);
    setBrief({ id: opportunityId, state: 'loading' });
    api.getBrief(opportunityId, applied, signal).then(
      (data) => { if (id === briefSeq.current) setBrief({ id: opportunityId, state: 'ready', data }); },
      (error) => { if (id === briefSeq.current) setBrief({ id: opportunityId, state: 'error', ...describeError(error) }); },
    );
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const parsed = api.parseKeywords(keywordText);
    // Invalid keywords are reported and nothing is sent; they are never silently altered.
    if (!parsed.ok) {
      setKeywordError(parsed.message);
      return;
    }
    setKeywordError(null);
    setApplied({ kinds, keywords: parsed.keywords, includeClosed });
  };

  const toggleKind = (kind: OpportunityKind, checked: boolean) =>
    setKinds((all) => (checked ? [...all, kind].slice(0, api.MAX_INTERESTS) : all.filter((k) => k !== kind)));

  return (
    <section aria-label="기회 준비 도우미" style={{ overflowWrap: 'anywhere', minWidth: 0 }} className="mx-auto grid max-w-6xl gap-6 p-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <section aria-labelledby="match-title" style={{ minWidth: 0 }} className="space-y-3">
        <h2 id="match-title" className="text-xl font-semibold">맞춤 기회 찾기</h2>
        <p className="rounded bg-slate-50 p-2 text-xs text-slate-600">{DISCLAIMER}</p>
        <p className="text-xs">질문에서 찾고 싶은 표현을 직접 키워드로 확인해 입력하세요. 자연어를 자동 해석하거나 LLM을 호출하지 않습니다.</p>
        <form onSubmit={submit} className="space-y-2 text-sm">
          <fieldset className="flex flex-wrap gap-2">
            <legend className="text-xs text-slate-600">관심 분류</legend>
            {(Object.keys(KIND_LABEL) as OpportunityKind[]).map((kind) => (
              <label key={kind} style={TOUCH_TARGET} className="flex items-center gap-1">
                <input type="checkbox" checked={kinds.includes(kind)} onChange={(e) => toggleKind(kind, e.target.checked)} />
                {KIND_LABEL[kind]}
              </label>
            ))}
          </fieldset>
          <input
            aria-label="관심 키워드"
            value={keywordText}
            onChange={(e) => {
              setKeywordText(e.target.value);
              setKeywordError(null);
            }}
            placeholder={`쉼표로 구분, 최대 ${api.MAX_INTERESTS}개, 각 ${api.MAX_KEYWORD_LENGTH}자 이하`}
            aria-invalid={keywordError ? true : undefined}
            aria-describedby={keywordError ? 'keyword-error' : undefined}
            className="w-full rounded border border-slate-300 px-2 py-1"
          />
          {keywordError && (
            <p id="keyword-error" role="alert" className="text-xs text-red-700">{keywordError}</p>
          )}
          <label style={TOUCH_TARGET} className="flex items-center gap-1">
            <input type="checkbox" checked={includeClosed} onChange={(e) => setIncludeClosed(e.target.checked)} />
            마감된 공고 포함
          </label>
          <button type="submit" style={TOUCH_TARGET} className="rounded bg-slate-800 px-3 py-1 text-white">맞춤 공고 보기</button>
        </form>

        {list.state === 'loading' && <p aria-busy="true" className="text-sm text-slate-500">맞춤 공고를 불러오는 중…</p>}
        {list.state === 'error' && <ErrorBox {...list} onRetry={reload} />}
        {list.state === 'ready' && (
          <>
            <ContextLine context={list.page.context} />
            <p className="text-xs text-slate-500">
              {list.page.provenance.notice} 평가 시각 {formatDateTime(list.page.evaluated_at)}
            </p>
            {!list.page.complete && (
              <p role="status" className="rounded bg-amber-50 p-2 text-xs text-amber-800">
                후보 공고를 {list.page.candidate_cap}건까지만 확인했습니다. 목록이 전부가 아닐 수 있습니다.
              </p>
            )}
            {list.page.omitted_count > 0 && (
              <p role="status" className="text-xs text-slate-500">
                형식이 올바르지 않은 공고 {list.page.omitted_count}건은 제외했습니다.
              </p>
            )}
            {list.items.length === 0 ? (
              <p className="text-sm text-slate-500">현재 소속과 조건에 맞는 공고가 없습니다.</p>
            ) : (
              <ul aria-label="맞춤 공고" className="space-y-2">
                {list.items.map((item) => <MatchCard key={item.opportunity.id} item={item} onBrief={openBrief} />)}
              </ul>
            )}
            {moreError && (
              <ErrorBox
                {...moreError}
                onRetry={moreError.conflict ? reload : loadMore}
                retryLabel={moreError.conflict ? '처음부터 다시 불러오기' : '다시 시도'}
              />
            )}
            {list.page.next_cursor && !moreError && (
              <button type="button" disabled={loadingMore} onClick={loadMore} style={TOUCH_TARGET} className="rounded border border-slate-300 px-3 py-1 text-sm">
                {loadingMore ? '불러오는 중…' : '더 보기'}
              </button>
            )}
          </>
        )}
      </section>

      <section aria-label="요약·절차" style={{ minWidth: 0 }} className="space-y-3">
        {!brief && <p className="text-sm text-slate-500">공고를 선택하면 원문 필드 기반 요약과 절차를 보여 줍니다.</p>}
        {brief?.state === 'loading' && <p aria-busy="true" className="text-sm text-slate-500">요약을 불러오는 중…</p>}
        {brief?.state === 'error' && <ErrorBox {...brief} onRetry={() => openBrief(brief.id)} />}
        {brief?.state === 'ready' && <><BriefPanel brief={brief.data} />{onSaved && <PreparationDraft key={`${brief.id}:${briefSeq.current}`} brief={brief.data} interests={applied} onSaved={onSaved} />}</>}
      </section>
    </section>
  );
}
