import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../lib/api';
import * as api from './api';
import * as savedApi from '../opportunities/api';
import type { SavedOpportunity } from '../opportunities/types';
import type { MatchPage, OpportunityBrief } from './types';
import PreparationDraft, { briefVersion } from './PreparationDraft';
import OpportunityAssistant from './OpportunityAssistant';

vi.mock('./api', async original => ({ ...await original<typeof import('./api')>(), getBrief: vi.fn(), listMatches: vi.fn() }));
vi.mock('../opportunities/api', () => ({ listSaved: vi.fn(), saveOpportunity: vi.fn(), addCheck: vi.fn(), newIdempotencyKey: vi.fn() }));

const ID = '10000000-0000-4000-8000-000000000001';
const INTERESTS = { kinds: [], keywords: ['장학'] };
const BRIEF: OpportunityBrief = {
  opportunity: { id: ID, title: '[DEMO] 장학 공고', organization: '', kind: 'scholarship',
    target_scope: { level: 'school', department_codes: [], academic_years: [] }, apply_starts_at: null,
    deadline_at: null, deadline_passed: false, submission_mode: 'info_only', source_kind: 'DEMO',
    needs_verification: true, eligibility: '가상 공고의 자격 원문', destination: null, original_url: null,
    source_url: null, checked_at: null, files: [], platform_receives_submission: false },
  match: { in_scope: true, score: 10, reasons: [] }, window: 'NO_DEADLINE', freshness: 'UNVERIFIED',
  procedure: [{ order: 1, code: 'CHECK_ORIGINAL', available: true, evidence_field: 'title', evidence_value: '원문', evidence_url: null }],
  cautions: [{ code: 'DEMO_SOURCE' }], recruitment: { status: 'NOT_CONNECTED', open_count: 0, items: [] },
  context: { memberships: [{ department_code: 'CSE', grade: 2 }], interest_kinds: [], interest_keywords: ['장학'] },
  evaluated_at: '2026-10-30T03:00:00Z', provenance: { generator: 'deterministic_rules_v1', ai_generated: false, eligibility_guaranteed: false, notice: '고정 규칙' },
};
const row = (overrides: Partial<SavedOpportunity> = {}): SavedOpportunity => ({
  opportunity_id: ID, status: 'interested', memo: '', revision: 1, self_reported_submitted_at: null,
  created_at: '2026-10-30T03:00:00Z', updated_at: '2026-10-30T03:00:00Z', checks: [], opportunity: BRIEF.opportunity, ...overrides,
});
const check = { id: 'check-one', text: '원문 확인하기', sort_order: 0, revision: 1, completed_at: null };
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (error: unknown) => void; const promise = new Promise<T>((r, j) => { resolve = r; reject = j; }); return { promise, resolve, reject }; }

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getBrief).mockResolvedValue(structuredClone(BRIEF));
  vi.mocked(api.listMatches).mockResolvedValue({
    items: [{ opportunity: BRIEF.opportunity, score: 10, reasons: [], window: BRIEF.window,
      freshness: BRIEF.freshness, checked_at: null, source_url: null, recruitment: BRIEF.recruitment }],
    next_cursor: null, candidate_cap: 200, candidates_scanned: 1, complete: true, omitted_count: 0,
    context: BRIEF.context, evaluated_at: BRIEF.evaluated_at, provenance: BRIEF.provenance,
  } satisfies MatchPage);
  vi.mocked(savedApi.listSaved).mockResolvedValue({ items: [] });
  vi.mocked(savedApi.saveOpportunity).mockResolvedValue(row());
  vi.mocked(savedApi.addCheck).mockResolvedValue(check);
  vi.mocked(savedApi.newIdempotencyKey).mockReturnValue('chk-same-intent');
});

function mount(onSaved = vi.fn()) { return { ...render(<PreparationDraft brief={BRIEF} interests={INTERESTS} onSaved={onSaved} />), onSaved }; }
function open() { fireEvent.click(screen.getByText('준비 초안 만들기')); fireEvent.change(screen.getByLabelText('준비 항목 초안 1'), { target: { value: check.text } }); }
async function review() { fireEvent.click(screen.getByText('준비 초안 검토')); await screen.findByRole('region', { name: '저장 전 확인' }); }
function confirm() { fireEvent.click(screen.getByLabelText('선택한 준비 항목을 내 기록에 추가하는 데 동의합니다')); fireEvent.click(screen.getByText('확인하고 내 준비에 저장')); }

describe('PreparationDraft: explicit consent, current source and existing preparation', () => {
  it('moves keyboard focus from open to editor to review and back to the cancel trigger', async () => {
    mount();
    const trigger = screen.getByRole('button', { name: '준비 초안 만들기' }); trigger.focus();
    expect(trigger).toHaveStyle({ minHeight: '24px' });
    fireEvent.click(trigger);
    expect(screen.getByRole('heading', { name: /^준비 초안 —/ })).toHaveFocus();
    expect(screen.getByLabelText('초안 항목 1 저장').closest('label')).toHaveStyle({ minHeight: '24px' });
    const reviewButton = screen.getByRole('button', { name: '준비 초안 검토' }); reviewButton.focus();
    expect(reviewButton).toHaveStyle({ minHeight: '24px' });
    fireEvent.click(reviewButton);
    expect(await screen.findByRole('heading', { name: '저장 전 확인' })).toHaveFocus();
    expect(screen.getByLabelText('선택한 준비 항목을 내 기록에 추가하는 데 동의합니다').closest('label')).toHaveStyle({ minHeight: '24px' });
    const cancel = screen.getByRole('button', { name: '초안 취소' }); cancel.focus(); fireEvent.click(cancel);
    expect(screen.getByRole('button', { name: '준비 초안 만들기' })).toHaveFocus();
    expect(savedApi.saveOpportunity).not.toHaveBeenCalled(); expect(savedApi.addCheck).not.toHaveBeenCalled();
  });

  it('returns focus to the editor when reviewing the draft again without losing input', async () => {
    mount(); open(); await review();
    fireEvent.click(screen.getByRole('button', { name: '초안 다시 편집' }));
    expect(screen.getByRole('heading', { name: /^준비 초안 —/ })).toHaveFocus();
    expect(screen.getByLabelText('준비 항목 초안 1')).toHaveValue(check.text);
    fireEvent.click(screen.getByRole('button', { name: '초안 취소' }));
    expect(screen.getByRole('button', { name: '준비 초안 만들기' })).toHaveFocus();
  });

  it('retains long unbroken evidence and applies intrinsic wrapping instead of truncating content', () => {
    const text = 'LongUnbrokenEvidence'.repeat(30);
    const brief = { ...BRIEF, opportunity: { ...BRIEF.opportunity, title: text, organization: text, eligibility: text },
      procedure: [{ ...BRIEF.procedure[0], evidence_value: text }] };
    render(<PreparationDraft brief={brief} interests={INTERESTS} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '준비 초안 만들기' }));
    expect(screen.getByRole('region', { name: '준비 초안 편집' })).toHaveStyle({ overflowWrap: 'anywhere', minWidth: '0' });
    expect(screen.getByRole('heading', { name: `준비 초안 — ${text}` })).toBeInTheDocument();
    expect(screen.getAllByText(text, { exact: false }).length).toBeGreaterThan(2);
  });

  it('editing, read-only review and cancellation make no writes', async () => {
    mount(); open(); await review();
    expect(savedApi.saveOpportunity).not.toHaveBeenCalled(); expect(savedApi.addCheck).not.toHaveBeenCalled();
    expect(screen.getByText('확인하고 내 준비에 저장')).toBeDisabled();
    fireEvent.click(screen.getByText('초안 취소'));
    expect(screen.queryByRole('region', { name: '준비 초안 편집' })).not.toBeInTheDocument();
    expect(savedApi.saveOpportunity).not.toHaveBeenCalled();
  });

  it('writes selected edits only after final consent, then confirms them by a server read', async () => {
    vi.mocked(savedApi.listSaved).mockResolvedValueOnce({ items: [] }).mockResolvedValueOnce({ items: [] }).mockResolvedValueOnce({ items: [row({ checks: [check] })] });
    const { onSaved } = mount(); open(); fireEvent.change(screen.getByLabelText('준비 메모 초안'), { target: { value: '내 메모' } });
    await review(); confirm();
    await screen.findByRole('status');
    expect(savedApi.saveOpportunity).toHaveBeenCalledWith(ID, '내 메모', expect.any(AbortSignal));
    expect(savedApi.addCheck).toHaveBeenCalledWith(ID, check.text, 0, 'chk-same-intent', expect.any(AbortSignal));
    expect(savedApi.listSaved).toHaveBeenCalledTimes(3);
    expect(onSaved).not.toHaveBeenCalled(); fireEvent.click(screen.getByText('내 준비 목록으로 이동')); expect(onSaved).toHaveBeenCalledOnce();
  });

  it('preserves an existing memo, state, completed check and sort order', async () => {
    const old = { ...check, id: 'old', text: '원래 기록', sort_order: 8, completed_at: '2026-10-30T02:00:00Z' };
    const existing = row({ memo: '기존 메모', status: 'preparing', checks: [old] });
    const added = { ...check, sort_order: 9 };
    vi.mocked(savedApi.addCheck).mockResolvedValue(added);
    vi.mocked(savedApi.listSaved).mockResolvedValueOnce({ items: [existing] }).mockResolvedValueOnce({ items: [existing] }).mockResolvedValueOnce({ items: [{ ...existing, checks: [old, added] }] });
    mount(); open(); await review(); expect(screen.getByText(/메모: 기존 메모 유지/)).toBeInTheDocument(); confirm(); await screen.findByRole('status');
    expect(savedApi.saveOpportunity).not.toHaveBeenCalled();
    expect(savedApi.addCheck).toHaveBeenCalledWith(ID, check.text, 9, 'chk-same-intent', expect.any(AbortSignal));
    expect(existing.memo).toBe('기존 메모'); expect(existing.status).toBe('preparing'); expect(existing.checks[0]).toEqual(old);
  });

  it('rejects changed source after consent before any write, but ignores evaluation clock alone', async () => {
    expect(briefVersion(BRIEF)).toBe(briefVersion({ ...BRIEF, evaluated_at: '2026-10-30T05:00:00Z' }));
    vi.mocked(api.getBrief).mockResolvedValueOnce(BRIEF).mockResolvedValueOnce({ ...BRIEF, opportunity: { ...BRIEF.opportunity, eligibility: '변경된 대상' } });
    mount(); open(); await review(); confirm();
    await screen.findByText(/확인 이후 공고/);
    expect(savedApi.saveOpportunity).not.toHaveBeenCalled(); expect(savedApi.addCheck).not.toHaveBeenCalled();
    expect(screen.getByLabelText('준비 항목 초안 1')).toHaveValue(check.text);
  });

  it('does not accept a generated/fake provenance as a reviewed rule source', async () => {
    vi.mocked(api.getBrief).mockResolvedValue({ ...BRIEF, provenance: { ...BRIEF.provenance, ai_generated: true } } as unknown as OpportunityBrief);
    mount(); open(); fireEvent.click(screen.getByText('준비 초안 검토')); await screen.findByRole('alert');
    expect(screen.queryByRole('region', { name: '저장 전 확인' })).not.toBeInTheDocument(); expect(savedApi.saveOpportunity).not.toHaveBeenCalled();
  });

  it('locks duplicate submissions synchronously and retains the exact key/body after an unknown check reply', async () => {
    const pending = deferred<typeof check>();
    vi.mocked(savedApi.addCheck).mockReturnValueOnce(pending.promise).mockResolvedValueOnce(check);
    vi.mocked(savedApi.listSaved).mockResolvedValueOnce({ items: [] }).mockResolvedValueOnce({ items: [] }).mockResolvedValueOnce({ items: [row()] }).mockResolvedValueOnce({ items: [row({ checks: [check] })] });
    mount(); open(); await review(); confirm();
    await waitFor(() => expect(savedApi.addCheck).toHaveBeenCalledOnce());
    const first = vi.mocked(savedApi.addCheck).mock.calls[0].slice(0, 4);
    fireEvent.click(screen.getByText('같은 요청으로 저장 다시 확인'));
    expect(savedApi.addCheck).toHaveBeenCalledOnce();
    await act(async () => pending.reject(new ApiError('NETWORK', 0)));
    await screen.findByRole('alert');
    fireEvent.click(screen.getByText('같은 요청으로 저장 다시 확인'));
    await screen.findByRole('status');
    expect(vi.mocked(savedApi.addCheck).mock.calls[1].slice(0, 4)).toEqual(first);
    expect(savedApi.newIdempotencyKey).toHaveBeenCalledOnce(); expect(savedApi.saveOpportunity).toHaveBeenCalledOnce();
  });

  it('does not claim completion when readback is missing and never recreates a removed preparation', async () => {
    vi.mocked(savedApi.listSaved).mockResolvedValueOnce({ items: [] }).mockResolvedValueOnce({ items: [] }).mockResolvedValueOnce({ items: [] }).mockResolvedValueOnce({ items: [] });
    mount(); open(); await review(); confirm(); await screen.findByRole('alert');
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('같은 요청으로 저장 다시 확인'));
    await screen.findByText(/삭제된 기록을 자동으로/);
    expect(savedApi.saveOpportunity).toHaveBeenCalledOnce(); expect(savedApi.addCheck).toHaveBeenCalledOnce();
  });

  it('keeps completed partial writes and retries only the uncertain item with its original key/body', async () => {
    const brief = { ...BRIEF, procedure: [...BRIEF.procedure, { ...BRIEF.procedure[0], order: 2, code: 'SELF_RECORD' as const }] };
    vi.mocked(api.getBrief).mockResolvedValue(brief);
    vi.mocked(savedApi.newIdempotencyKey).mockReturnValueOnce('chk-first').mockReturnValueOnce('chk-second');
    const second = { ...check, id: 'check-two', text: '두 번째 준비', sort_order: 1 };
    vi.mocked(savedApi.addCheck).mockResolvedValueOnce(check).mockRejectedValueOnce(new ApiError('NETWORK', 0)).mockResolvedValueOnce(second);
    vi.mocked(savedApi.listSaved).mockResolvedValueOnce({ items: [] }).mockResolvedValueOnce({ items: [] })
      .mockResolvedValueOnce({ items: [row({ checks: [check] })] }).mockResolvedValueOnce({ items: [row({ checks: [check, second] })] });
    render(<PreparationDraft brief={brief} interests={INTERESTS} onSaved={vi.fn()} />);
    open(); fireEvent.change(screen.getByLabelText('준비 항목 초안 2'), { target: { value: second.text } });
    await review(); confirm(); await screen.findByRole('alert');
    const uncertain = vi.mocked(savedApi.addCheck).mock.calls[1].slice(0, 4);
    fireEvent.click(screen.getByText('같은 요청으로 저장 다시 확인')); await screen.findByRole('status');
    expect(savedApi.addCheck).toHaveBeenCalledTimes(3);
    expect(vi.mocked(savedApi.addCheck).mock.calls[2].slice(0, 4)).toEqual(uncertain);
    expect(savedApi.newIdempotencyKey).toHaveBeenCalledTimes(2); expect(savedApi.saveOpportunity).toHaveBeenCalledOnce();
  });

  it('rejects an empty selection and overlong code-point input before even reviewing', async () => {
    mount(); open(); fireEvent.click(screen.getByLabelText('초안 항목 1 저장'));
    fireEvent.click(screen.getByText('준비 초안 검토')); await screen.findByRole('alert');
    fireEvent.click(screen.getByLabelText('초안 항목 1 저장'));
    fireEvent.change(screen.getByLabelText('준비 항목 초안 1'), { target: { value: '😀'.repeat(201) } });
    fireEvent.click(screen.getByText('준비 초안 검토'));
    expect(api.getBrief).not.toHaveBeenCalled(); expect(savedApi.saveOpportunity).not.toHaveBeenCalled();
  });

  it('preserves edited input but requires a second review after the first source refresh changed', async () => {
    const changed = { ...BRIEF, opportunity: { ...BRIEF.opportunity, eligibility: '새로운 자격 원문' } };
    vi.mocked(api.getBrief).mockResolvedValue(changed);
    mount(); open(); fireEvent.click(screen.getByText('준비 초안 검토'));
    await screen.findByText(/공고 또는 현재 소속·대상 정보가 바뀌었습니다/);
    expect(screen.getByLabelText('준비 항목 초안 1')).toHaveValue(check.text);
    expect(screen.queryByRole('region', { name: '저장 전 확인' })).not.toBeInTheDocument();
    await review(); expect(savedApi.saveOpportunity).not.toHaveBeenCalled();
  });

  it('aborts an old session and never follows its late write response with another write/read/callback', async () => {
    const pending = deferred<SavedOpportunity>(); vi.mocked(savedApi.saveOpportunity).mockReturnValue(pending.promise);
    const view = mount(); open(); await review(); confirm();
    await waitFor(() => expect(savedApi.saveOpportunity).toHaveBeenCalledOnce());
    const signal = vi.mocked(savedApi.saveOpportunity).mock.calls[0][2];
    view.unmount(); expect(signal?.aborted).toBe(true);
    await act(async () => pending.resolve(row()));
    expect(savedApi.addCheck).not.toHaveBeenCalled(); expect(savedApi.listSaved).toHaveBeenCalledTimes(2); expect(view.onSaved).not.toHaveBeenCalled();
  });

  it('StrictMode discards the first pending review generation', async () => {
    const first = deferred<OpportunityBrief>(); vi.mocked(api.getBrief).mockReturnValueOnce(first.promise);
    const view = render(<StrictMode><PreparationDraft brief={BRIEF} interests={INTERESTS} onSaved={vi.fn()} /></StrictMode>);
    open(); fireEvent.click(screen.getByText('준비 초안 검토')); view.unmount();
    await act(async () => first.resolve(BRIEF));
    expect(savedApi.listSaved).not.toHaveBeenCalled(); expect(savedApi.saveOpportunity).not.toHaveBeenCalled();
  });

  it.each([401, 403])('discards all draft data and retry intent immediately on %i', async status => {
    vi.mocked(savedApi.addCheck).mockRejectedValue(new ApiError(status === 401 ? 'UNAUTHORIZED' : 'FORBIDDEN', status));
    mount(); open(); fireEvent.change(screen.getByLabelText('준비 메모 초안'), { target: { value: '폐기할 개인 메모' } });
    await review(); confirm(); await screen.findByText(/로그인 또는 권한이 변경/);
    expect(screen.queryByRole('region', { name: '준비 초안 편집' })).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('폐기할 개인 메모')).not.toBeInTheDocument();
    expect(screen.queryByText('같은 요청으로 저장 다시 확인')).not.toBeInTheDocument();
    expect(savedApi.addCheck).toHaveBeenCalledOnce();
  });

  it('the shell generation replacement discards account A drafts and its late write before account B can use the screen', async () => {
    const pending = deferred<SavedOpportunity>(); vi.mocked(savedApi.saveOpportunity).mockReturnValue(pending.promise);
    const onSaved = vi.fn();
    const view = render(<OpportunityAssistant sessionGeneration="A" onSaved={onSaved} />);
    fireEvent.click(await screen.findByRole('button', { name: '요약·절차 보기' }));
    await screen.findByText('준비 초안 만들기'); open();
    fireEvent.change(screen.getByLabelText('준비 메모 초안'), { target: { value: 'A의 비공개 메모' } });
    await review(); confirm(); await waitFor(() => expect(savedApi.saveOpportunity).toHaveBeenCalledOnce());
    const signal = vi.mocked(savedApi.saveOpportunity).mock.calls[0][2];
    view.rerender(<OpportunityAssistant sessionGeneration="B" onSaved={onSaved} />);
    expect(signal?.aborted).toBe(true);
    await screen.findByRole('button', { name: '요약·절차 보기' });
    expect(screen.queryByRole('region', { name: '준비 초안 편집' })).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('A의 비공개 메모')).not.toBeInTheDocument();
    await act(async () => pending.resolve(row()));
    expect(savedApi.addCheck).not.toHaveBeenCalled(); expect(savedApi.listSaved).toHaveBeenCalledTimes(2); expect(onSaved).not.toHaveBeenCalled();
    expect(api.listMatches).toHaveBeenCalledTimes(2);
  });
});
