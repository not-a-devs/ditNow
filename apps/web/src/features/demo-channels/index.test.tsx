import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../lib/api';
import * as api from './api';
import DemoChannels, { OperationalGates } from './index';

vi.mock('./api', async () => ({ ...await vi.importActual<typeof import('./api')>('./api'), listDemoChannels: vi.fn(), createDemoChannel: vi.fn(), cancelDemoChannel: vi.fn() }));
const free: api.DemoChannelRequest = { id: '00000000-0000-4000-8000-000000000001', purpose: 'study', requested_kind: 'FREE', title: '[DEMO] 스터디 자유 채널(가상)', status: 'CREATED', revision: 1, created_at: '2026-10-30T00:00:00Z', official_badge: false, real_review: 'NOT_OPERATED', record_source: 'DEMO', persistence: 'PROCESS_MEMORY' };
const official: api.DemoChannelRequest = { ...free, id: '00000000-0000-4000-8000-000000000002', requested_kind: 'OFFICIAL', status: 'PENDING_REVIEW', title: '[DEMO] 스터디 공식 채널 신청(가상·실제 검토 없음)' };
const list = (items: api.DemoChannelRequest[]): api.DemoChannelList => ({ items, per_user_limit: 20, record_source: 'DEMO', persistence: 'PROCESS_MEMORY' });
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.listDemoChannels).mockResolvedValue(list([])); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('가상 채널 신청', () => {
  it('공식 승인·배지·소유자·권한 필드나 승인 상태를 거부한다', () => {
    expect(api.isDemoChannelRequest(free)).toBe(true);
    expect(api.isDemoChannelRequest(official)).toBe(true);
    for (const changed of [{ official_badge: true }, { status: 'APPROVED' }, { owner_id: 'x' }, { role: 'admin' }, { record_source: 'MARIADB' }, { real_review: 'APPROVED' }, { title: '임의 제목' }])
      expect(api.isDemoChannelRequest({ ...official, ...changed })).toBe(false);
    expect(api.isDemoChannelRequest({ ...official, status: 'CREATED' })).toBe(false);
  });
  it('동의 없이는 신청할 수 없고 고정 필드만 보낸다', async () => {
    vi.mocked(api.createDemoChannel).mockResolvedValue(official);
    render(<DemoChannels />); await screen.findByText('가상 신청이 없습니다.');
    const submit = screen.getByRole('button', { name: '가상 신청' });
    expect(submit).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/공식 채널\(가상 신청/));
    fireEvent.click(screen.getByLabelText(/가상 체험이며/));
    vi.mocked(api.listDemoChannels).mockResolvedValue(list([official]));
    fireEvent.click(submit);
    expect(await screen.findByText(/실제 검토·승인·공식 배지는 제공되지 않습니다/)).toBeInTheDocument();
    expect(vi.mocked(api.createDemoChannel).mock.calls[0][0]).toEqual({ purpose: 'study', requested_kind: 'OFFICIAL', consent: true });
    expect(screen.getByText(/검토 대기 · 실제 검토·승인 없음/)).toBeInTheDocument();
  });
  it('취소는 현재 개정을 보내고 409면 목록을 다시 불러온다', async () => {
    vi.mocked(api.listDemoChannels).mockResolvedValue(list([free]));
    vi.mocked(api.cancelDemoChannel).mockRejectedValueOnce(new ApiError('CONFLICT', 409));
    render(<DemoChannels />);
    fireEvent.click(await screen.findByRole('button', { name: `${free.title} 취소` }));
    expect(await screen.findByRole('alert')).toHaveTextContent('목록을 다시 불러왔습니다');
    expect(vi.mocked(api.cancelDemoChannel).mock.calls[0][0]).toMatchObject({ id: free.id, revision: 1 });
  });
  it('503과 401을 구별하고 401이면 목록을 지운다', async () => {
    vi.mocked(api.listDemoChannels).mockRejectedValueOnce(new ApiError('UNAVAILABLE', 503));
    render(<DemoChannels />); expect(await screen.findByRole('alert')).toHaveTextContent('연결을 준비');
    vi.mocked(api.listDemoChannels).mockResolvedValueOnce(list([free]));
    fireEvent.click(screen.getByRole('button', { name: '목록 다시 불러오기' }));
    await screen.findByText(free.title);
    vi.mocked(api.listDemoChannels).mockRejectedValueOnce(new ApiError('UNAUTHORIZED', 401));
    fireEvent.click(screen.getByRole('button', { name: '목록 다시 불러오기' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('로그인이 만료');
    expect(screen.queryByText(free.title)).not.toBeInTheDocument();
  });
  it('POST 성공 뒤 GET에 같은 영수증이 없으면 성공이 아니며 다시 불러오기 전까지 재신청을 막는다', async () => {
    vi.mocked(api.createDemoChannel).mockResolvedValue(free);
    render(<DemoChannels />); await screen.findByText('가상 신청이 없습니다.');
    fireEvent.click(screen.getByLabelText(/가상 체험이며/));
    fireEvent.click(screen.getByRole('button', { name: '가상 신청' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('확인하지 못했습니다');
    expect(screen.queryByText(/신청이 생성되었습니다/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/가상 체험이며/));
    expect(screen.getByRole('button', { name: '가상 신청' })).toBeDisabled();
    // A mismatched revision is also not a confirmed receipt.
    vi.mocked(api.listDemoChannels).mockResolvedValueOnce(list([{ ...free, revision: 2 }]));
    fireEvent.click(screen.getByRole('button', { name: '목록 다시 불러오기' }));
    expect(await screen.findByText(/이전 신청이 목록에 있는지 확인/)).toBeInTheDocument();
    expect(api.createDemoChannel).toHaveBeenCalledTimes(1);
  });
  it.each([new TypeError('network'), new ApiError('UNAVAILABLE', 503)])('POST 결과를 알 수 없으면 자동 재시도하지 않는다 %j', async cause => {
    vi.mocked(api.createDemoChannel).mockRejectedValue(cause);
    render(<DemoChannels />); await screen.findByText('가상 신청이 없습니다.');
    fireEvent.click(screen.getByLabelText(/가상 체험이며/));
    fireEvent.click(screen.getByRole('button', { name: '가상 신청' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('중복 신청을 막기 위해');
    expect(screen.getByRole('button', { name: '가상 신청' })).toBeDisabled();
    expect(screen.getByLabelText(/가상 체험이며/)).not.toBeChecked();
    expect(api.createDemoChannel).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: '목록 다시 불러오기' }));
    await screen.findByText(/이전 신청이 목록에 있는지 확인/);
    expect(screen.getByRole('button', { name: '가상 신청' })).toBeDisabled();
    expect(api.createDemoChannel).toHaveBeenCalledTimes(1);
  });
  it('DELETE 성공 뒤 행이 남아 있으면 취소 완료로 표시하지 않는다', async () => {
    vi.mocked(api.listDemoChannels).mockResolvedValue(list([free]));
    vi.mocked(api.cancelDemoChannel).mockResolvedValue(free.id);
    render(<DemoChannels />);
    fireEvent.click(await screen.findByRole('button', { name: `${free.title} 취소` }));
    expect(await screen.findByRole('alert')).toHaveTextContent('취소를 확인하지 못했습니다');
    expect(screen.queryByText('가상 신청을 취소했습니다.')).not.toBeInTheDocument();
  });
  it('403이면 같은 세대에서 모든 조작을 잠그고 새 세대에서만 다시 읽는다', async () => {
    vi.mocked(api.listDemoChannels).mockResolvedValueOnce(list([free]));
    const view = render(<DemoChannels sessionGeneration={1} />);
    const cancelButton = await screen.findByRole('button', { name: `${free.title} 취소` });
    fireEvent.click(screen.getByLabelText(/가상 체험이며/));
    vi.mocked(api.cancelDemoChannel).mockRejectedValueOnce(new ApiError('FORBIDDEN', 403));
    fireEvent.click(cancelButton);
    expect(await screen.findByRole('alert')).toHaveTextContent('접근 권한');
    expect(screen.queryByText(free.title)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/가상 체험이며/)).not.toBeChecked();
    expect(screen.getByLabelText(/가상 체험이며/)).toBeDisabled();
    expect(screen.getByRole('button', { name: '목록 다시 불러오기' })).toBeDisabled();
    expect(api.listDemoChannels).toHaveBeenCalledTimes(1);
    view.rerender(<DemoChannels sessionGeneration={2} />);
    await screen.findByText('가상 신청이 없습니다.');
    expect(api.listDemoChannels).toHaveBeenCalledTimes(2);
  });
  it('이전 세대의 늦은 생성 응답은 새 세대의 동의·목록을 바꾸지 않는다', async () => {
    let resolveA!: (value: api.DemoChannelRequest) => void;
    vi.mocked(api.createDemoChannel).mockImplementationOnce(() => new Promise(resolve => { resolveA = resolve; }));
    const view = render(<DemoChannels sessionGeneration={1} />); await screen.findByText('가상 신청이 없습니다.');
    fireEvent.click(screen.getByLabelText(/가상 체험이며/));
    fireEvent.click(screen.getByRole('button', { name: '가상 신청' }));
    view.rerender(<DemoChannels sessionGeneration={2} />);
    await screen.findByText('가상 신청이 없습니다.');
    fireEvent.click(screen.getByLabelText(/가상 체험이며/));
    resolveA(free); await Promise.resolve(); await Promise.resolve();
    expect(screen.getByLabelText(/가상 체험이며/)).toBeChecked();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(api.listDemoChannels).toHaveBeenCalledTimes(2);
  });
  it('운영 게이트 안내는 읽기 전용이며 요청을 보내지 않는다', () => {
    render(<OperationalGates />);
    expect(screen.getByText(/다른 사용자로 보기, 관리자 체험, 권한 시뮬레이션 기능은 없습니다/)).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(api.listDemoChannels).not.toHaveBeenCalled();
  });
});
