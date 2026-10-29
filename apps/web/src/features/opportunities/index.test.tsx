// UI states and checklist retry semantics against the real shared transport (fetch stubbed).
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import OpportunitiesPage from './index';
import type { OpportunitySummary, SavedOpportunity } from './types';

const OID = '00000000-0000-4000-8000-000000000001';

const SUMMARY: OpportunitySummary = {
  id: OID,
  kind: 'scholarship',
  title: '[DEMO] 가상 외부 장학금',
  organization: '가상 장학재단',
  target_scope: { level: 'school', department_codes: [], academic_years: [] },
  apply_starts_at: null,
  deadline_at: '2026-11-06T03:00:00Z',
  deadline_passed: false,
  submission_mode: 'external_document_submission',
  source_kind: 'DEMO',
  needs_verification: true,
};

const SAVED: SavedOpportunity = {
  opportunity_id: OID,
  status: 'preparing',
  memo: '',
  self_reported_submitted_at: null,
  revision: 2,
  created_at: '2026-10-30T03:00:00Z',
  updated_at: '2026-10-30T03:00:00Z',
  checks: [],
  opportunity: SUMMARY,
};

type Reply = { status: number; body: unknown } | 'pending' | 'network';
type Handler = (method: string, path: string, init: RequestInit) => Reply;

const ok = (data: unknown): Reply => ({ status: 200, body: { data } });
const fail = (status: number, code: string): Reply => ({ status, body: { code, message: 'x', request_id: '12345678-1234-1234-1234-123456789012' } });

function stub(handler: Handler) {
  const fetch = vi.fn((url: string, init: RequestInit = {}) => {
    const reply = handler(init.method ?? 'GET', new URL(url).pathname, init);
    if (reply === 'pending') return new Promise<Response>(() => {});
    if (reply === 'network') return Promise.reject(new TypeError('offline'));
    return Promise.resolve(new Response(JSON.stringify(reply.body), { status: reply.status }));
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

const postCalls = (fetch: ReturnType<typeof stub>) =>
  fetch.mock.calls
    .filter(([, init]) => init?.method === 'POST')
    .map(([, init]) => ({ key: (init!.headers as Record<string, string>)['Idempotency-Key'], body: JSON.parse(init!.body as string) }));

describe('OpportunitiesPage states', () => {
  it('shows loading for both panels while requests are in flight', () => {
    stub(() => 'pending');
    render(<OpportunitiesPage />);
    expect(screen.getByText('목록을 불러오는 중…')).toBeInTheDocument();
    expect(screen.getByText('내 준비 목록을 불러오는 중…')).toBeInTheDocument();
  });

  it('shows the not-ready message on 503 without fake data', async () => {
    stub(() => fail(503, 'UNAVAILABLE'));
    render(<OpportunitiesPage />);
    expect(await screen.findAllByText('서버 연결 준비 중입니다. 아직 이용할 수 없습니다.')).toHaveLength(2);
    expect(screen.queryByText(SUMMARY.title)).not.toBeInTheDocument();
  });

  it('separates 401 on the private list from a working public list', async () => {
    stub((_m, path) => (path.endsWith('/me/saved-opportunities') ? fail(401, 'UNAUTHORIZED') : ok({ items: [SUMMARY], next_cursor: null })));
    render(<OpportunitiesPage />);
    expect(await screen.findByText(SUMMARY.title)).toBeInTheDocument();
    expect(await screen.findByText('로그인이 필요합니다.')).toBeInTheDocument();
    expect(screen.getByText('요청 ID: 12345678-1234-1234-1234-123456789012')).toBeInTheDocument();
  });

  it('retries the public list after a network error', async () => {
    let attempts = 0;
    stub((_m, path) => {
      if (path.endsWith('/opportunities')) return ++attempts === 1 ? 'network' : ok({ items: [SUMMARY], next_cursor: null });
      return ok({ items: [] });
    });
    render(<OpportunitiesPage />);
    expect(await screen.findByText('서버에 연결할 수 없습니다. 네트워크 상태를 확인하세요.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }));
    expect(await screen.findByText(SUMMARY.title)).toBeInTheDocument();
    expect(attempts).toBe(2);
  });
});

describe('checklist add intent', () => {
  function world(postReplies: Reply[]) {
    let saved = SAVED;
    const fetch = stub((method, path, init) => {
      if (path.endsWith('/opportunities')) return ok({ items: [SUMMARY], next_cursor: null });
      if (path.endsWith('/me/saved-opportunities')) return ok({ items: [saved] });
      if (method === 'POST') {
        const reply = postReplies.shift() ?? fail(500, 'INTERNAL');
        if (reply !== 'pending' && reply !== 'network' && reply.status === 201) {
          const body = JSON.parse(init.body as string);
          saved = { ...saved, checks: [...saved.checks, { id: `c-${saved.checks.length}`, text: body.text, sort_order: body.sort_order, completed_at: null, revision: 1 }] };
        }
        return reply;
      }
      return fail(500, 'INTERNAL');
    });
    render(<OpportunitiesPage />);
    return fetch;
  }

  const input = () => screen.getByRole('textbox', { name: '준비 항목' }) as HTMLInputElement;

  it('keeps the text after failure and retries with the same key and body', async () => {
    const fetch = world([fail(503, 'UNAVAILABLE'), 'network', { status: 201, body: { data: {} } }]);
    fireEvent.change(await screen.findByRole('textbox', { name: '준비 항목' }), { target: { value: '  추천서 ' } });
    fireEvent.click(screen.getByRole('button', { name: '추가' }));
    await screen.findByText('서버 연결 준비 중입니다. 아직 이용할 수 없습니다.');
    expect(input().value).toBe('  추천서 ');

    fireEvent.click(await screen.findByRole('button', { name: '다시 시도' }));
    await screen.findByText('서버에 연결할 수 없습니다. 네트워크 상태를 확인하세요.');
    expect(input().value).toBe('  추천서 ');

    fireEvent.click(await screen.findByRole('button', { name: '다시 시도' }));
    await screen.findByText('추천서');
    await waitFor(() => expect(input().value).toBe(''));

    const posts = postCalls(fetch);
    expect(posts).toHaveLength(3);
    expect(new Set(posts.map((p) => p.key)).size).toBe(1);
    expect(posts.every((p) => p.body.text === '추천서' && p.body.sort_order === 0)).toBe(true);
    expect(screen.getByRole('button', { name: '추가' })).toBeInTheDocument();
  });

  it('uses a new key when the text changes after a failure', async () => {
    const fetch = world([fail(503, 'UNAVAILABLE'), { status: 201, body: { data: {} } }]);
    fireEvent.change(await screen.findByRole('textbox', { name: '준비 항목' }), { target: { value: '추천서' } });
    fireEvent.click(screen.getByRole('button', { name: '추가' }));
    await screen.findByText('서버 연결 준비 중입니다. 아직 이용할 수 없습니다.');
    fireEvent.change(input(), { target: { value: '성적증명서' } });
    fireEvent.click(await screen.findByRole('button', { name: '추가' }));
    await screen.findByText('성적증명서');
    const [first, second] = postCalls(fetch);
    expect(first.key).not.toBe(second.key);
    expect(second.body).toEqual({ text: '성적증명서', sort_order: 0 });
  });

  it('uses a different key for each successful add', async () => {
    const fetch = world([{ status: 201, body: { data: {} } }, { status: 201, body: { data: {} } }]);
    for (const text of ['A 서류', 'B 서류']) {
      fireEvent.change(await screen.findByRole('textbox', { name: '준비 항목' }), { target: { value: text } });
      fireEvent.click(await screen.findByRole('button', { name: '추가' }));
      await screen.findByText(text);
    }
    const [a, b] = postCalls(fetch);
    expect(a.key).not.toBe(b.key);
    expect([a.body.sort_order, b.body.sort_order]).toEqual([0, 1]);
  });

  it('shows a 409 replay conflict without clearing the input', async () => {
    world([fail(409, 'CONFLICT')]);
    fireEvent.change(await screen.findByRole('textbox', { name: '준비 항목' }), { target: { value: '추천서' } });
    fireEvent.click(screen.getByRole('button', { name: '추가' }));
    expect(await screen.findByText('현재 상태와 충돌합니다. 최신 내용을 다시 불러왔습니다.')).toBeInTheDocument();
    expect(input().value).toBe('추천서');
  });
});
