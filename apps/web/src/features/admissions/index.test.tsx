import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import AdmissionsPage from './index';
import { intentTracker, isGuide, isOverview, loadGuides, loadOverview, safeSource, writeApplication, type Application } from './api';

const CYCLE = '11111111-1111-4111-8111-111111111111';
const TRACK = '22222222-2222-4222-8222-222222222222';
const ID = '33333333-3333-4333-8333-333333333333';
const now = '2026-10-30T00:00:00Z';
const policy = { cycle_id: CYCLE, name: '가상 테스트 모집', revision: 1, tracks: [{id:TRACK,label:'가상 테스트 전형'}], opens_at:'2026-10-29T00:00:00Z', closes_at:'2026-10-31T00:00:00Z', withdrawal_closes_at:'2026-11-01T00:00:00Z', max_applications:1, source_kind:'DEMO' };
const row: Application = { id:ID, cycle_id:CYCLE, track_id:TRACK, demo_alias:'가상 지원자 A', motivation:'career_exploration', state:'draft', revision:1, policy_revision:1, created_at:now,updated_at:now,source_kind:'DEMO', documents:'BLOCKED',admission_result:'BLOCKED',payment_refund:'BLOCKED' };
const guide = {id:ID,title:'미확인 안내',summary:'원문 내용 미확인',revision:1,source_kind:'UNKNOWN',source_url:null,checked_at:null,schedules:[],faqs:[]};
const reply = (data: unknown, status = 200) => new Response(JSON.stringify({data}),{status});
const failure = (status: number, code: string) => new Response(JSON.stringify({code,message:'sensitive-server-detail'}),{status});
type Handler = (url: URL, init: RequestInit) => Response | Promise<Response>;
function stub(handler: Handler) { const fetch = vi.fn((url: string, init: RequestInit = {}) => Promise.resolve(handler(new URL(url),init))); vi.stubGlobal('fetch',fetch); return fetch; }

describe('admissions boundaries and transport', () => {
  it('uses the real shared transport with one prefix and caller intent headers', async () => {
    const fetch = stub((_url,init) => reply(init.method ? row : {items:[],offset:0,has_more:false}));
    await loadGuides();
    await writeApplication(`/admissions/me/applications/${ID}`, {expected_revision:1}, 'demo-key-123456789','PATCH');
    expect(fetch.mock.calls[0][0]).toBe(`${window.location.origin}/api/v1/admissions/guides?offset=0&limit=20`);
    expect(fetch.mock.calls[1][0]).toBe(`${window.location.origin}/api/v1/admissions/me/applications/${ID}`);
    expect(fetch.mock.calls[1][1]!.headers).toMatchObject({'Idempotency-Key':'demo-key-123456789'});
    expect(fetch.mock.calls[1][1]!.method).toBe('PATCH');
  });
  it('supports an explicitly configured absolute API base', async () => {
    vi.stubEnv('VITE_API_BASE_URL','https://api.example.test/api/v1');
    const fetch = stub(() => reply({policies:[],applications:[],source_kind:'DEMO'}));
    await loadOverview();
    expect(fetch.mock.calls[0][0]).toBe('https://api.example.test/api/v1/admissions/me');
  });
  it('rejects owner identities, unsafe or uncited official material', () => {
    expect(isOverview({policies:[policy],applications:[{...row,owner_id:'private-user'}],source_kind:'DEMO'})).toBe(false);
    expect(isGuide({...guide,source_kind:'OFFICIAL_PUBLIC'})).toBe(false);
    expect(isGuide({...guide,source_kind:'OFFICIAL_PUBLIC',source_url:'javascript:alert(1)',checked_at:now})).toBe(false);
    expect(safeSource('https://user:password@example.test')).toBe(false);
    expect(safeSource('https://example.test/guide')).toBe(true);
  });
  it('keeps same intent keys, rotates changed payloads and separates resources', () => {
    let n = 0; const tracker = intentTracker(() => `key-${++n}`);
    expect(tracker.key('/a',{revision:1})).toBe(tracker.key('/a',{revision:1}));
    expect(tracker.key('/a',{revision:2})).toBe('key-2');
    expect(tracker.key('/b',{revision:2})).toBe('key-3');
    tracker.done('/a'); expect(tracker.key('/a',{revision:2})).toBe('key-4');
  });
});

describe('admissions page', () => {
  it('shows loading and fails closed on 503 without invented records', async () => {
    stub(() => failure(503,'UNAVAILABLE'));
    render(<AdmissionsPage />);
    expect(screen.getByText(/입학 안내와 가상 지원 내역을 확인/)).toBeInTheDocument();
    expect(await screen.findAllByRole('alert')).toHaveLength(2);
    expect(screen.queryByRole('button',{name:'가상 초안 저장'})).not.toBeInTheDocument();
    expect(screen.queryByText('sensitive-server-detail')).not.toBeInTheDocument();
  });
  it('shows empty verified content and no policy without creating a mock application', async () => {
    stub(url => reply(url.pathname.endsWith('/guides') ? {items:[],offset:0,has_more:false} : {applications:[],policies:[],source_kind:'DEMO'}));
    render(<AdmissionsPage />);
    expect(await screen.findByText(/검증해 등록한 안내 자료가 없습니다/)).toBeInTheDocument();
    expect(await screen.findByText(/가상 전형·정책이 없습니다/)).toBeInTheDocument();
    expect(screen.queryByLabelText('가상 별칭')).not.toBeInTheDocument();
  });
  it('separates public guide content from a private 401 response', async () => {
    stub(url => url.pathname.endsWith('/guides') ? reply({items:[guide],offset:0,has_more:false}) : failure(401,'UNAUTHORIZED'));
    render(<AdmissionsPage />);
    expect(await screen.findByText('미확인 안내')).toBeInTheDocument();
    expect(await screen.findByRole('alert')).toHaveTextContent('로그인이 필요한');
    expect(screen.getByText(/출처 미확인/)).toBeInTheDocument();
    expect(screen.queryByRole('link',{name:'근거 원문'})).not.toBeInTheDocument();
  });
  it('retries an unchanged draft with the same key and rotates it after editing', async () => {
    const fetch = stub((url,init) => init.method ? failure(409,'CONFLICT') : reply(url.pathname.endsWith('/guides') ? {items:[],offset:0,has_more:false} : {applications:[],policies:[policy],source_kind:'DEMO'}));
    render(<AdmissionsPage />);
    const save = await screen.findByRole('button',{name:'가상 초안 저장'});
    fireEvent.click(save); await screen.findByRole('alert');
    expect(screen.getByLabelText('가상 별칭')).toHaveValue('가상 지원자 A');
    fireEvent.click(save); await waitFor(() => expect(fetch.mock.calls.filter(([,i]) => i?.method)).toHaveLength(2));
    await waitFor(() => expect(save).toBeEnabled());
    fireEvent.change(screen.getByLabelText('가상 별칭'),{target:{value:'가상 지원자 B'}});
    fireEvent.click(save); await waitFor(() => expect(fetch.mock.calls.filter(([,i]) => i?.method)).toHaveLength(3));
    const headers = fetch.mock.calls.filter(([,i]) => i?.method).map(([,i]) => i!.headers as Record<string,string>);
    expect(headers[0]['Idempotency-Key']).toBe(headers[1]['Idempotency-Key']);
    expect(headers[1]['Idempotency-Key']).not.toBe(headers[2]['Idempotency-Key']);
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });
  it('runs a virtual create/edit/submit/withdraw flow using server records', async () => {
    let current: Application | null = null;
    const fetch = stub((url,init) => {
      if (!init.method) return reply(url.pathname.endsWith('/guides') ? {items:[],offset:0,has_more:false} : {applications:[],policies:[policy],source_kind:'DEMO'});
      const body = JSON.parse(String(init.body));
      current = url.pathname.endsWith('/applications') ? row : {...current!, revision:current!.revision+1, ...(init.method === 'PATCH' ? {motivation:body.motivation} : {state:url.pathname.endsWith('/submit') ? 'submitted' as const : 'withdrawal_requested' as const})};
      return reply(current);
    });
    render(<AdmissionsPage />);
    fireEvent.click(await screen.findByRole('button',{name:'가상 초안 저장'}));
    expect(await screen.findByText('가상 지원자 A · 가상 작성 중')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:'초안 수정'}));
    fireEvent.change(screen.getByLabelText('가상 지원 동기'),{target:{value:'project_learning'}});
    fireEvent.click(screen.getByRole('button',{name:'가상 초안 수정'}));
    await screen.findByText(/개정 2/);
    fireEvent.click(screen.getByRole('button',{name:'가상 제출'}));
    expect(await screen.findByText('가상 지원자 A · 가상 제출됨')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:'가상 취소 요청'}));
    expect(await screen.findByText('가상 지원자 A · 가상 취소 요청됨')).toBeInTheDocument();
    expect(fetch.mock.calls.filter(([,i]) => i?.method)).toHaveLength(4);
    expect(screen.queryByRole('button',{name:'환불'})).not.toBeInTheDocument();
    expect(screen.getByText(/서류 도착·면접·합격·납부·환불: 미구현/)).toBeInTheDocument();
  });
  it('removes personal records on a revoked write while keeping guide content', async () => {
    stub((url,init) => init.method ? failure(403,'FORBIDDEN') : reply(url.pathname.endsWith('/guides') ? {items:[guide],offset:0,has_more:false} : {applications:[row],policies:[policy],source_kind:'DEMO'}));
    render(<AdmissionsPage />);
    fireEvent.click(await screen.findByRole('button',{name:'가상 제출'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('접근할 권한');
    expect(screen.queryByText('가상 지원자 A · 가상 작성 중')).not.toBeInTheDocument();
    expect(screen.getByText('미확인 안내')).toBeInTheDocument();
  });
});
