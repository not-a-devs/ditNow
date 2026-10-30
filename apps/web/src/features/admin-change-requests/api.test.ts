import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as lib from '../../lib/api';
import * as api from './api';

vi.mock('../../lib/api', async () => ({ ...await vi.importActual<typeof import('../../lib/api')>('../../lib/api'), requestData: vi.fn() }));
const proposal: api.Proposal = {
  id: '00000000-0000-4000-8000-000000000001', target_code: 'STUDENT_DEMO_A', proposal_scope: 'DEPARTMENT_STUDENT', reason_code: 'ACADEMIC_DEMO',
  state: 'DRAFT', revision: 1, created_at: '2026-10-30T02:00:00Z', updated_at: '2026-10-30T02:00:00Z', submitted_at: null, withdrawn_at: null,
  record_source: 'DEMO', storage: 'PROCESS_MEMORY', official_effect: false, restart_reset: true, replayed: false,
};
const createBody: api.CreateBody = { target_code: 'STUDENT_DEMO_A', proposal_scope: 'DEPARTMENT_STUDENT', reason_code: 'ACADEMIC_DEMO', consent: true };
const submitted: api.Proposal = { ...proposal, state: 'SUBMITTED', revision: 2, updated_at: '2026-10-30T02:01:00Z', submitted_at: '2026-10-30T02:01:00Z' };
const withdrawn: api.Proposal = { ...submitted, state: 'WITHDRAWN', revision: 3, updated_at: '2026-10-30T02:02:00Z', withdrawn_at: '2026-10-30T02:02:00Z' };
const list: api.ProposalList ={ items: [proposal], owner_cap: 20, record_source: 'DEMO', storage: 'PROCESS_MEMORY', official_effect: false, restart_reset: true };
beforeEach(() => vi.mocked(lib.requestData).mockReset());

describe('관리 변경 제안 API 계약', () => {
  it('고정 코드·DEMO 표식만 허용하고 소유자·권한·공식 효력 필드를 거부한다', () => {
    expect(api.isProposal(proposal)).toBe(true);
    expect(api.isProposalList(list)).toBe(true);
    for (const changed of [{ owner_id: 'x' }, { role: 'ADMIN' }, { official_effect: true }, { state: 'APPROVED' }, { target_code: 'REAL' },
      { record_source: 'OFFICIAL' }, { storage: 'DB' }, { revision: 0 }, { revision: '1' }, { id: '../x' }, { created_at: '2026-10-30' },
      { withdrawn_at: '2026-10-30T02:00:00Z' }]) expect(api.isProposal({ ...proposal, ...changed })).toBe(false);
    expect(api.isProposalList({ ...list, items: [proposal, proposal] })).toBe(false);
    expect(api.isProposalList({ ...list, owner_cap: 0 })).toBe(false);
    expect(api.isProposalList({ ...list, official_effect: true })).toBe(false);
  });
  it('requestData 경로에 /api/v1 접두사를 다시 붙이지 않고 no-store·멱등 키를 보낸다', async () => {
    vi.mocked(lib.requestData).mockResolvedValueOnce(list).mockResolvedValueOnce(proposal).mockResolvedValueOnce(submitted).mockResolvedValueOnce(withdrawn);
    await api.loadProposals();
    await api.createProposal(createBody, 'intent-key-000001');
    await api.submitProposal(proposal.id, 1, 'intent-key-000002');
    await api.withdrawProposal(proposal.id, 2);
    const calls = vi.mocked(lib.requestData).mock.calls;
    expect(calls.map(call => call[0])).toEqual(['/admin-change-requests', '/admin-change-requests', `/admin-change-requests/${proposal.id}/submit`, `/admin-change-requests/${proposal.id}?revision=2`]);
    expect(calls.every(call => !call[0].includes('/api/v1') && call[1]?.cache === 'no-store')).toBe(true);
    expect((calls[1][1]?.headers as Record<string, string>)['Idempotency-Key']).toBe('intent-key-000001');
    expect(JSON.parse(String(calls[2][1]?.body))).toEqual({ expected_revision: 1 });
    expect(calls[3][1]?.method).toBe('DELETE');
  });
  it('형식이 틀린 응답과 비정상 id는 거부한다', async () => {
    vi.mocked(lib.requestData).mockResolvedValueOnce({ ...proposal, owner_id: 'u' });
    await expect(api.submitProposal(proposal.id, 1, 'intent-key-000003')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    await expect(api.withdrawProposal('../../auth', 1)).rejects.toBeInstanceOf(lib.ApiError);
    expect(lib.requestData).toHaveBeenCalledTimes(1);
  });
  it('공개 API는 비정상 id를 동기 throw 없이 Promise reject로 일관되게 알린다', () => {
    let promise: Promise<unknown> | undefined;
    expect(() => { promise = api.submitProposal('../x', 1, 'intent-key-000009'); }).not.toThrow();
    return expect(promise).rejects.toBeInstanceOf(lib.ApiError);
  });
  it('형식은 맞지만 요청과 다른 생성 영수증(다른 대상·범위·사유, DRAFT 1 아님)은 거부한다', async () => {
    for (const bad of [{ ...proposal, target_code: 'STUDENT_DEMO_B' }, { ...proposal, proposal_scope: 'YEAR_STUDENT' },
      { ...proposal, reason_code: 'CORRECTION_DEMO' }, submitted, { ...proposal, revision: 2 }]) {
      vi.mocked(lib.requestData).mockResolvedValueOnce(bad);
      await expect(api.createProposal(createBody, 'intent-key-000010')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    }
    vi.mocked(lib.requestData).mockResolvedValueOnce({ ...proposal, replayed: true });
    await expect(api.createProposal(createBody, 'intent-key-000010')).resolves.toMatchObject({ revision: 1, replayed: true });
  });
  it('다른 id·변하지 않은 상태·잘못된 개정의 제출/철회 영수증은 거부한다', async () => {
    const otherId = '00000000-0000-4000-8000-000000000002';
    for (const bad of [proposal, { ...submitted, id: otherId }, { ...submitted, revision: 3 }, withdrawn]) {
      vi.mocked(lib.requestData).mockResolvedValueOnce(bad);
      await expect(api.submitProposal(proposal.id, 1, 'intent-key-000011')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    }
    for (const bad of [submitted, { ...withdrawn, id: otherId }, { ...withdrawn, revision: 2 }]) {
      vi.mocked(lib.requestData).mockResolvedValueOnce(bad);
      await expect(api.withdrawProposal(proposal.id, 2)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    }
    const directWithdraw = { ...proposal, state: 'WITHDRAWN' as const, revision: 2, withdrawn_at: '2026-10-30T02:01:00Z' };
    vi.mocked(lib.requestData).mockResolvedValueOnce(directWithdraw);
    await expect(api.withdrawProposal(proposal.id, 1)).resolves.toMatchObject({ state: 'WITHDRAWN', revision: 2 });
  });
  it('같은 의도는 같은 키, 다른 의도·clear 후에는 새 키', () => {
    let n = 0; const tracker = api.intentTracker(() => `key-${++n}`);
    expect(tracker.key({ a: 1 })).toBe('key-1'); expect(tracker.key({ a: 1 })).toBe('key-1');
    expect(tracker.key({ a: 2 })).toBe('key-2'); tracker.clear(); expect(tracker.key({ a: 2 })).toBe('key-3');
  });
  it('영수증은 새 목록의 id·상태·개정이 모두 같을 때만 일치', () => {
    expect(api.matchesReceipt(list, proposal)).toBe(true);
    expect(api.matchesReceipt(list, { ...proposal, revision: 2 })).toBe(false);
    expect(api.matchesReceipt(list, { ...proposal, state: 'SUBMITTED' })).toBe(false);
  });
});
