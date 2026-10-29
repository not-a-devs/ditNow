import { StrictMode } from 'react';
import { act, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../lib/api';
import * as api from './api';
import { ProgramsPanel } from './PrivatePanels';

afterEach(() => vi.restoreAllMocks());
function prepare() {
  vi.spyOn(api, 'listPrograms').mockResolvedValue({ items: [], policy_id: 'demo-review', policy_basis: 'DEMO' });
  let rejectOld!: (reason: unknown) => void;
  const calls = vi.spyOn(api, 'listApplications')
    .mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectOld = reject; }))
    .mockResolvedValue([]);
  return { calls, reject: (error: unknown) => rejectOld(error) };
}

describe('개인 프로그램 요청 세대', () => {
  it.each([401, 403])('권한 재확인 뒤 이전 화면의 늦은 %s는 새 화면을 차단하지 않는다', async status => {
    const pending = prepare(); const onAuthError = vi.fn();
    const view = render(<ProgramsPanel canApply onAuthError={onAuthError} />);
    await waitFor(() => expect(pending.calls).toHaveBeenCalledTimes(1));
    view.rerender(<ProgramsPanel canApply={false} onAuthError={onAuthError} />);
    view.rerender(<ProgramsPanel canApply onAuthError={onAuthError} />);
    await waitFor(() => expect(pending.calls).toHaveBeenCalledTimes(2));
    await act(async () => pending.reject(new ApiError(status === 401 ? 'UNAUTHORIZED' : 'FORBIDDEN', status)));
    expect(onAuthError).not.toHaveBeenCalled();
  });
  it('StrictMode의 이전 요청이 늦게 거부되어도 현재 세대는 보존한다', async () => {
    const pending = prepare(); const onAuthError = vi.fn();
    render(<StrictMode><ProgramsPanel canApply onAuthError={onAuthError} /></StrictMode>);
    await waitFor(() => expect(pending.calls).toHaveBeenCalledTimes(2));
    await act(async () => pending.reject(new ApiError('UNAUTHORIZED', 401)));
    expect(onAuthError).not.toHaveBeenCalled();
  });
  it('현재 세대의 권한 실패는 즉시 상위로 전달한다', async () => {
    vi.spyOn(api, 'listPrograms').mockResolvedValue({ items: [], policy_id: 'demo-review', policy_basis: 'DEMO' });
    vi.spyOn(api, 'listApplications').mockRejectedValue(new ApiError('FORBIDDEN', 403));
    const onAuthError = vi.fn();
    render(<ProgramsPanel canApply onAuthError={onAuthError} />);
    await waitFor(() => expect(onAuthError).toHaveBeenCalledWith('applications', expect.objectContaining({ status: 403 })));
  });
});
