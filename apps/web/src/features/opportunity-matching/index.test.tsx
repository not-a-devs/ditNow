// UI states for FR-OPP-002 matching against the real shared transport (fetch stubbed).
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import OpportunityMatchingPage from './index';
import type { OpportunitySummary } from '../opportunities/types';
import type { MatchItem, MatchPage, OpportunityBrief } from './types';

const OID = '00000000-0000-4000-8000-000000000001';
const OID2 = '00000000-0000-4000-8000-000000000002';
const REQUEST_ID = '12345678-1234-1234-1234-123456789012';

const summary = (id: string, title: string): OpportunitySummary => ({
  id,
  kind: 'scholarship',
  title,
  organization: '가상 장학재단',
  target_scope: { level: 'department', department_codes: ['CSE'], academic_years: [] },
  apply_starts_at: null,
  deadline_at: '2026-11-06T03:00:00Z',
  deadline_passed: false,
  submission_mode: 'external_document_submission',
  source_kind: 'DEMO',
  needs_verification: true,
});

const item = (id: string, title: string, overrides: Partial<MatchItem> = {}): MatchItem => ({
  opportunity: summary(id, title),
  score: 25,
  reasons: [
    { code: 'DEPARTMENT_MATCH', source_field: 'target_scope.department_codes', value: 'CSE' },
    { code: 'DEADLINE_SOON', source_field: 'deadline_at', value: null },
  ],
  window: 'OPEN',
  freshness: 'CURRENT',
  checked_at: '2026-10-29T03:00:00Z',
  source_url: 'https://example.test/notice',
  recruitment: { status: 'NOT_CONNECTED', open_count: 0, items: [] },
  ...overrides,
});

const PROVENANCE = {
  generator: 'deterministic_rules_v1',
  ai_generated: false,
  eligibility_guaranteed: false,
  notice: '서버의 고정 규칙으로 정렬한 참고 목록입니다.',
} as const;

const page = (items: MatchItem[], overrides: Partial<MatchPage> = {}): MatchPage => ({
  items,
  next_cursor: null,
  candidate_cap: 200,
  candidates_scanned: items.length,
  complete: true,
  omitted_count: 0,
  context: { memberships: [{ department_code: 'CSE', grade: 2 }], interest_kinds: [], interest_keywords: [] },
  evaluated_at: '2026-10-30T03:00:00Z',
  provenance: PROVENANCE,
  ...overrides,
});

const BRIEF: OpportunityBrief = {
  opportunity: {
    ...summary(OID, '[DEMO] 컴퓨터공학과 장학'),
    eligibility: '원문 그대로의 자격 문구',
    destination: null,
    original_url: 'https://example.test/notice',
    source_url: null,
    checked_at: '2026-10-29T03:00:00Z',
    files: [],
    platform_receives_submission: false,
  },
  match: { in_scope: false, score: 0, reasons: [] },
  window: 'OPEN',
  freshness: 'STALE',
  procedure: [
    { order: 1, code: 'CHECK_ORIGINAL', available: true, evidence_field: 'original_url', evidence_value: null, evidence_url: 'https://example.test/notice' },
    { order: 2, code: 'DOWNLOAD_FORM', available: true, evidence_field: 'files', evidence_value: 'form.hwp', evidence_url: 'javascript:alert(1)' },
    { order: 3, code: 'SUBMIT_TO_DESTINATION', available: false, evidence_field: 'destination', evidence_value: null, evidence_url: null },
  ],
  cautions: [{ code: 'NOT_ELIGIBILITY_DECISION' }, { code: 'OUT_OF_SCOPE' }, { code: 'STALE_SOURCE' }],
  recruitment: { status: 'UNAVAILABLE', open_count: 0, items: [] },
  context: page([]).context,
  evaluated_at: '2026-10-30T03:00:00Z',
  provenance: PROVENANCE,
};

type Reply = { status: number; body: unknown } | 'network' | Promise<Response>;
type Handler = (url: URL) => Reply;

const ok = (data: unknown): Reply => ({ status: 200, body: { data } });
const fail = (status: number, code: string): Reply => ({ status, body: { code, message: 'x', request_id: REQUEST_ID } });

function stub(handler: Handler) {
  const fetch = vi.fn((url: string, _init?: RequestInit) => {
    const reply = handler(new URL(url));
    if (reply instanceof Promise) return reply;
    if (reply === 'network') return Promise.reject(new TypeError('offline'));
    return Promise.resolve(new Response(JSON.stringify(reply.body), { status: reply.status }));
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

function deferred() {
  let resolve!: (r: Response) => void;
  const promise = new Promise<Response>((r) => { resolve = r; });
  return { promise, resolve: (data: unknown) => resolve(new Response(JSON.stringify({ data }), { status: 200 })) };
}

afterEach(() => vi.unstubAllGlobals());

describe('OpportunityMatchingPage', () => {
  it('shows loading then the disclaimer, context, reasons, freshness and safe source link', async () => {
    stub(() => ok(page([
      item(OID, '컴퓨터공학과 장학'),
      item(OID2, '오래된 공고', { freshness: 'STALE', source_url: 'javascript:alert(1)', reasons: [] }),
    ])));
    render(<OpportunityMatchingPage />);
    expect(screen.getByText('맞춤 공고를 불러오는 중…')).toBeInTheDocument();
    expect(screen.getByText(/AI 생성 결과가 아니며 지원 자격을 보장하지 않습니다/)).toBeInTheDocument();
    await screen.findByText('컴퓨터공학과 장학');
    expect(screen.getByText('현재 소속 기준: CSE 2학년')).toBeInTheDocument();
    expect(screen.getByText(/현재 소속 학과가 공고 대상 학과에 포함 \(CSE\)/)).toBeInTheDocument();
    expect(screen.getByText(/마감 7일 이내/)).toBeInTheDocument();
    expect(screen.getAllByText('DEMO 가상 공고')).toHaveLength(2);
    expect(screen.getByText(/원문 확인 30일 경과/)).toBeInTheDocument();
    const links = screen.getAllByRole('link', { name: '원문 보기' });
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute('href', 'https://example.test/notice');
    expect(links[0]).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.getByText('원문 링크 없음')).toBeInTheDocument();
    expect(screen.getByText('일치한 규칙 없음')).toBeInTheDocument();
    expect(document.querySelector('a[href^="javascript"]')).toBeNull();
  });

  it.each([
    [503, 'UNAVAILABLE', '서버 연결 준비 중입니다. 아직 이용할 수 없습니다.'],
    [401, 'UNAUTHORIZED', '로그인이 필요합니다.'],
    [403, 'FORBIDDEN', '현재 학적 소속이 확인되지 않아 맞춤 공고를 볼 수 없습니다.'],
    [400, 'VALIDATION', '입력값을 확인하세요.'],
  ])('shows the %s error with request id', async (status, code, message) => {
    stub(() => fail(status, code));
    render(<OpportunityMatchingPage />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(message);
    expect(alert).toHaveTextContent(REQUEST_ID);
  });

  it('retries after a network error', async () => {
    let calls = 0;
    stub(() => (++calls === 1 ? 'network' : ok(page([item(OID, '복구된 공고')]))));
    render(<OpportunityMatchingPage />);
    fireEvent.click(await screen.findByRole('button', { name: '다시 시도' }));
    await screen.findByText('복구된 공고');
  });

  it('shows empty, incomplete and omitted states', async () => {
    stub(() => ok(page([], { complete: false, omitted_count: 2, context: { memberships: [], interest_kinds: [], interest_keywords: [] } })));
    render(<OpportunityMatchingPage />);
    await screen.findByText('현재 소속과 조건에 맞는 공고가 없습니다.');
    expect(screen.getByText(/후보 공고를 200건까지만 확인했습니다/)).toBeInTheDocument();
    expect(screen.getByText('형식이 올바르지 않은 공고 2건은 제외했습니다.')).toBeInTheDocument();
    expect(screen.getByText(/확인된 학과·학년 소속 없음/)).toBeInTheDocument();
  });

  it('sends interests and filters from the form', async () => {
    const fetch = stub(() => ok(page([])));
    render(<OpportunityMatchingPage />);
    await screen.findByText('현재 소속과 조건에 맞는 공고가 없습니다.');
    fireEvent.click(screen.getByLabelText('공모전'));
    fireEvent.change(screen.getByLabelText('관심 키워드'), { target: { value: 'AI, ai, 데이터' } });
    fireEvent.click(screen.getByLabelText('마감된 공고 포함'));
    fireEvent.click(screen.getByRole('button', { name: '맞춤 공고 보기' }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    const url = new URL(fetch.mock.calls[1][0]);
    expect(url.searchParams.getAll('interest_kind')).toEqual(['contest']);
    expect(url.searchParams.getAll('interest_keyword')).toEqual(['AI', '데이터']);
    expect(url.searchParams.get('include_closed')).toBe('true');
  });

  it('shows a keyword validation message and sends nothing for an over-long or invisible keyword', async () => {
    const fetch = stub(() => ok(page([])));
    render(<OpportunityMatchingPage />);
    await screen.findByText('현재 소속과 조건에 맞는 공고가 없습니다.');
    const input = screen.getByLabelText('관심 키워드');
    for (const [value, message] of [
      ['😀'.repeat(21), '20자 이하'],
      ['장학 금', '보이지 않는 문자'],
    ]) {
      fireEvent.change(input, { target: { value } });
      fireEvent.click(screen.getByRole('button', { name: '맞춤 공고 보기' }));
      expect(await screen.findByRole('alert')).toHaveTextContent(message);
      expect(input).toHaveAttribute('aria-invalid', 'true');
      expect(input).toHaveValue(value);
    }
    expect(fetch).toHaveBeenCalledTimes(1);

    fireEvent.change(input, { target: { value: '😀'.repeat(20) } });
    expect(screen.queryByRole('alert')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '맞춤 공고 보기' }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(new URL(fetch.mock.calls[1][0]).searchParams.get('interest_keyword')).toBe('😀'.repeat(20));
  });

  it('aborts a superseded request and all requests on unmount', async () => {
    const first = deferred();
    let calls = 0;
    const fetch = stub(() => (++calls === 1 ? first.promise : new Promise<Response>(() => {})));
    const { unmount } = render(<OpportunityMatchingPage />);
    fireEvent.click(screen.getByRole('button', { name: '맞춤 공고 보기' }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(fetch.mock.calls[0][1]?.signal?.aborted).toBe(true);
    expect(fetch.mock.calls[1][1]?.signal?.aborted).toBe(false);
    unmount();
    expect(fetch.mock.calls[1][1]?.signal?.aborted).toBe(true);
  });

  it('ignores a stale response that arrives after a newer request', async () => {
    const first = deferred();
    let calls = 0;
    stub(() => (++calls === 1 ? first.promise : ok(page([item(OID2, '새 조건 결과')]))));
    render(<OpportunityMatchingPage />);
    fireEvent.click(screen.getByRole('button', { name: '맞춤 공고 보기' }));
    await screen.findByText('새 조건 결과');
    first.resolve(page([item(OID, '이전 조건 결과')]));
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByText('이전 조건 결과')).toBeNull();
    expect(screen.getByText('새 조건 결과')).toBeInTheDocument();
  });

  it('loads more with the cursor and offers a restart on 409', async () => {
    const fetch = stub((url) => {
      const cursor = url.searchParams.get('cursor');
      if (!cursor) return ok(page([item(OID, '첫 페이지')], { next_cursor: '10.0123456789abcdef' }));
      return fail(409, 'CONFLICT');
    });
    render(<OpportunityMatchingPage />);
    fireEvent.click(await screen.findByRole('button', { name: '더 보기' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('그 사이 결과가 바뀌었습니다');
    expect(new URL(fetch.mock.calls[1][0]).searchParams.get('cursor')).toBe('10.0123456789abcdef');
    expect(screen.getByText('첫 페이지')).toBeInTheDocument();
    fireEvent.click(within(alert).getByRole('button', { name: '처음부터 다시 불러오기' }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    expect(new URL(fetch.mock.calls[2][0]).searchParams.has('cursor')).toBe(false);
  });

  it('appends the next page', async () => {
    stub((url) => (url.searchParams.get('cursor')
      ? ok(page([item(OID2, '둘째 페이지')]))
      : ok(page([item(OID, '첫 페이지')], { next_cursor: '10.0123456789abcdef' }))));
    render(<OpportunityMatchingPage />);
    fireEvent.click(await screen.findByRole('button', { name: '더 보기' }));
    await screen.findByText('둘째 페이지');
    expect(screen.getByText('첫 페이지')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '더 보기' })).toBeNull();
  });

  it('renders the brief with original eligibility, procedure evidence, cautions and safe links', async () => {
    stub((url) => (url.pathname.endsWith('/brief') ? ok(BRIEF) : ok(page([item(OID, '컴퓨터공학과 장학')]))));
    render(<OpportunityMatchingPage />);
    fireEvent.click(await screen.findByRole('button', { name: '요약·절차 보기' }));
    const panel = await screen.findByRole('article', { name: '공고 요약' });
    expect(within(panel).getByText('원문 그대로의 자격 문구')).toBeInTheDocument();
    expect(within(panel).getByText('현재 소속이 대상 범위에 포함되지 않음')).toBeInTheDocument();
    const steps = within(panel).getByRole('list', { name: '지원 절차' });
    expect(within(steps).getAllByRole('listitem')).toHaveLength(3);
    expect(within(steps).getByText(/제출처 정보 없음/)).toBeInTheDocument();
    expect(within(steps).getAllByRole('link')).toHaveLength(1);
    expect(panel.querySelector('a[href^="javascript"]')).toBeNull();
    const cautions = within(panel).getByRole('list', { name: '주의 사항' });
    expect(cautions).toHaveTextContent('지원 자격 판정이 아닙니다');
    expect(cautions).toHaveTextContent('대상 범위에 포함되지 않습니다');
    expect(within(panel).getByText('팀원 모집 정보를 불러오지 못했습니다.')).toBeInTheDocument();
  });

  it('shows a brief error with retry', async () => {
    stub((url) => (url.pathname.endsWith('/brief') ? fail(404, 'NOT_FOUND') : ok(page([item(OID, '컴퓨터공학과 장학')]))));
    render(<OpportunityMatchingPage />);
    fireEvent.click(await screen.findByRole('button', { name: '요약·절차 보기' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('더 이상 공개되지 않은 공고');
  });

  it('shows linked recruitment references without links to private data', async () => {
    stub(() => ok(page([item(OID, '공모전', {
      recruitment: {
        status: 'AVAILABLE',
        open_count: 2,
        items: [{ id: 'rec-1', title: '가상 팀원 모집', field: 'AI', roles: ['백엔드'], deadline_at: '2026-11-02T03:00:00Z', matched_keywords: ['AI'] }],
      },
    })])));
    render(<OpportunityMatchingPage />);
    await screen.findByText('연결된 모집 중 팀원 모집 2건');
    expect(screen.getByText(/가상 팀원 모집 · AI/)).toHaveTextContent('관심 키워드: AI');
  });
});
