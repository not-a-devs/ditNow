import { StrictMode } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../lib/api';
import * as api from './api';
import ProfilePage from './index';

vi.mock('./api', async () => ({ ...await vi.importActual<typeof import('./api')>('./api'), loadProfile: vi.fn(), saveProfile: vi.fn() }));
const profile: api.Profile = { display_name: '가상 읽기전용 실명', department_name: '가상 학과', academic_year: 1, skills: [], interests: [], bio: '', revision: 1, updated_at: '2026-10-30T00:00:00Z', policy: { revision: 1, editable_fields: ['skills', 'interests', 'bio'], record_source: 'DEMO' }, record_source: 'DEMO', visibility: 'SELF_ONLY', identity_editable: false, replayed: false };
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.loadProfile).mockResolvedValue(profile); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
async function loaded() { render(<ProfilePage />); await screen.findByText(profile.display_name); }

describe('개인 활동 프로필', () => {
  it('최소 본인/가상 응답만 허용하고 신원·권한 필드와 새제품 필드를 거부한다', () => {
    expect(api.isProfile(profile)).toBe(true);
    for (const changed of [{ user_id: 'private' }, { roles: ['admin'] }, { nickname: 'new' }, { identity_editable: true }, { record_source: 'OFFICIAL' }, { policy: { ...profile.policy, editable_fields: ['display_name'] } }]) expect(api.isProfile({ ...profile, ...changed })).toBe(false);
    expect(api.isProfile({ ...profile, bio: '🙂'.repeat(500) })).toBe(true);
    expect(api.isProfile({ ...profile, bio: '🙂'.repeat(501) })).toBe(false);
  });
  it('원장은 읽기전용으로 표시하고 허용된 활동 필드만 저장한다', async () => {
    vi.mocked(api.saveProfile).mockResolvedValue({ ...profile, bio: '가상 소개', revision: 2 });
    await loaded(); expect(screen.queryByDisplayValue(profile.display_name)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('가상 소개'), { target: { value: '가상 소개' } });
    fireEvent.click(screen.getByRole('button', { name: '활동 필드 저장' }));
    await screen.findByText(/개인 활동 필드를 저장했습니다/);
    expect(vi.mocked(api.saveProfile).mock.calls[0][0]).toEqual({ skills: [], interests: [], bio: '가상 소개', expected_revision: 1, expected_policy_revision: 1 });
  });
  it('503과 없는 프로필을 구별하고 자동 생성하지 않는다', async () => {
    vi.mocked(api.loadProfile).mockRejectedValueOnce(new ApiError('UNAVAILABLE', 503)).mockRejectedValueOnce(new ApiError('NOT_FOUND', 404));
    render(<ProfilePage />); expect(await screen.findByRole('alert')).toHaveTextContent('연결을 준비');
    fireEvent.click(screen.getByRole('button', { name: /프로필 다시 조회/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('자동 생성하지 않습니다');
    expect(api.saveProfile).not.toHaveBeenCalled();
  });
  it('실패 입력과 요청 키를 보존하고 변경 입력은 키를 회전한다', async () => {
    vi.mocked(api.saveProfile).mockRejectedValue(new ApiError('NETWORK', 0)); await loaded();
    fireEvent.change(screen.getByLabelText('가상 소개'), { target: { value: '보존할 가상 입력' } });
    fireEvent.click(screen.getByRole('button', { name: '활동 필드 저장' })); await screen.findByRole('alert');
    expect(screen.getByLabelText('가상 소개')).toHaveValue('보존할 가상 입력');
    fireEvent.click(screen.getByRole('button', { name: '활동 필드 저장' })); await waitFor(() => expect(api.saveProfile).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByRole('button', { name: '활동 필드 저장' })).toBeEnabled());
    fireEvent.change(screen.getByLabelText('가상 소개'), { target: { value: '새 의도' } });
    fireEvent.click(screen.getByRole('button', { name: '활동 필드 저장' })); await waitFor(() => expect(api.saveProfile).toHaveBeenCalledTimes(3));
    const calls = vi.mocked(api.saveProfile).mock.calls; expect(calls[0][1]).toBe(calls[1][1]); expect(calls[1][1]).not.toBe(calls[2][1]);
  });
  it.each([401, 403])('현재 권한 %s 실패는 개인 프로필과 초안을 지운다', async status => {
    vi.mocked(api.saveProfile).mockRejectedValueOnce(new ApiError(status === 401 ? 'UNAUTHORIZED' : 'FORBIDDEN', status)); await loaded();
    fireEvent.change(screen.getByLabelText('가상 소개'), { target: { value: '지워야할입력' } });
    fireEvent.click(screen.getByRole('button', { name: '활동 필드 저장' })); await screen.findByRole('alert');
    expect(screen.queryByText(profile.display_name)).not.toBeInTheDocument(); expect(screen.queryByLabelText('가상 소개')).not.toBeInTheDocument();
  });
  it('정책의 허용목록이 비어 있으면 조회만 제공한다', async () => {
    vi.mocked(api.loadProfile).mockResolvedValueOnce({ ...profile, policy: { ...profile.policy, editable_fields: [] } });
    await loaded(); expect(screen.getByLabelText('가상 소개')).toBeDisabled(); expect(screen.getByRole('button', { name: '활동 필드 저장' })).toBeDisabled();
  });
  it.each([['bio'], ['skills', 'interests', 'bio']] as api.EditableField[][])('쉼표 포함 단일 항목을 소개 수정 때 원형 보존한다: %j', async (...fields) => {
    // Vitest spreads array cases; reconstruct the allowed list from this row.
    const editable_fields = fields as api.EditableField[];
    const current = { ...profile, skills: ['C,C++', 'Python'], interests: ['데이터, 분석'], policy: { ...profile.policy, editable_fields } };
    vi.mocked(api.loadProfile).mockResolvedValueOnce(current);
    vi.mocked(api.saveProfile).mockResolvedValueOnce({ ...current, bio: '새 가상 소개', revision: 2 });
    await loaded();
    expect(screen.getByLabelText('기술 · 한 줄에 한 항목')).toHaveValue('C,C++\nPython');
    fireEvent.change(screen.getByLabelText('가상 소개'), { target: { value: '새 가상 소개' } });
    fireEvent.click(screen.getByRole('button', { name: '활동 필드 저장' }));
    await screen.findByText(/개인 활동 필드를 저장했습니다/);
    expect(vi.mocked(api.saveProfile).mock.calls[0][0]).toMatchObject({ skills: ['C,C++', 'Python'], interests: ['데이터, 분석'], bio: '새 가상 소개' });
  });
  it('StrictMode와 계정 세대 변경 뒤 과거 응답을 폐기한다', async () => {
    let resolveOld!: (value: api.Profile) => void;
    vi.mocked(api.loadProfile).mockImplementationOnce(() => new Promise(done => { resolveOld = done; })).mockResolvedValue({ ...profile, display_name: '새 세대 가상 실명' });
    const view = render(<StrictMode><ProfilePage sessionGeneration={1} /></StrictMode>);
    await screen.findByText('새 세대 가상 실명'); await act(async () => resolveOld(profile));
    expect(screen.queryByText(profile.display_name)).not.toBeInTheDocument();
    view.rerender(<StrictMode><ProfilePage sessionGeneration={2} /></StrictMode>);
    await screen.findByText('새 세대 가상 실명');
  });
  it('저장 중 화면 제거는 취소하며 늦은 응답은 다음 화면에 반영하지 않는다', async () => {
    let resolve!: (value: api.Profile) => void; vi.mocked(api.saveProfile).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
    const view = render(<ProfilePage />); await screen.findByText(profile.display_name);
    fireEvent.click(screen.getByRole('button', { name: '활동 필드 저장' })); const signal = vi.mocked(api.saveProfile).mock.calls[0][2]!;
    view.unmount(); expect(signal.aborted).toBe(true); await act(async () => resolve({ ...profile, bio: '늦은 응답' }));
    expect(document.body).not.toHaveTextContent('늦은 응답');
  });
  it('실제 공통 전송은 /profiles/me와 CAS/정책/멱등 헤더만 사용한다', async () => {
    const actual = await vi.importActual<typeof import('./api')>('./api');
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: profile }), { status: 200 })); vi.stubGlobal('fetch', fetch);
    await actual.saveProfile({ skills: [], interests: [], bio: '', expected_revision: 1, expected_policy_revision: 1 }, 'test-intent-key-0001');
    expect(fetch.mock.calls[0][0]).toMatch(/\/api\/v1\/profiles\/me$/);
    expect(fetch.mock.calls[0][1]).toMatchObject({ method: 'PUT', cache: 'no-store', headers: { 'Idempotency-Key': 'test-intent-key-0001' } });
  });
});
