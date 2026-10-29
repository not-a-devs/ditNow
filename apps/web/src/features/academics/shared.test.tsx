import { StrictMode } from 'react';
import { act, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../lib/api';
import { useAction } from './shared';

// main.tsx renders under StrictMode, which runs effect setup → cleanup → setup on mount.
type Hook = ReturnType<typeof useAction>;

function mountStrict(onAuth: (error: unknown) => void) {
  const hook: { current: Hook | null } = { current: null };
  function Harness() {
    const action = useAction(onAuth);
    hook.current = action;
    return <p>{action.busy ? 'busy' : 'idle'}|{action.error}</p>;
  }
  const view = render(<StrictMode><Harness /></StrictMode>);
  return { hook: () => hook.current!, ...view };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

describe('useAction under StrictMode', () => {
  it('reports success and clears busy after the remount cycle', async () => {
    const onAuth = vi.fn();
    const onDone = vi.fn();
    const { hook } = mountStrict(onAuth);
    let ok: boolean | undefined;
    await act(async () => { ok = await hook().run(async () => 'saved', onDone); });
    expect(ok).toBe(true);
    expect(onDone).toHaveBeenCalledExactlyOnceWith('saved');
    expect(screen.getByText(/^idle\|$/)).toBeInTheDocument();
    expect(onAuth).not.toHaveBeenCalled();
  });

  it('shows the failure message and clears busy', async () => {
    const onAuth = vi.fn();
    const { hook } = mountStrict(onAuth);
    let ok: boolean | undefined;
    await act(async () => { ok = await hook().run(async () => { throw new ApiError('INTERNAL', 500); }, vi.fn()); });
    expect(ok).toBe(false);
    expect(screen.getByText(/^idle\|.+/)).toBeInTheDocument();
    expect(onAuth).not.toHaveBeenCalled();
  });

  it.each([401, 403])('forwards %i to the parent handler', async status => {
    const onAuth = vi.fn();
    const { hook } = mountStrict(onAuth);
    const failure = new ApiError(status === 401 ? 'UNAUTHORIZED' : 'FORBIDDEN', status);
    await act(async () => { await hook().run(async () => { throw failure; }, vi.fn()); });
    expect(onAuth).toHaveBeenCalledExactlyOnceWith(failure);
    expect(screen.getByText(/^idle\|/)).toBeInTheDocument();
  });

  it.each(['success', 'failure', 'auth'] as const)('ignores a %s result that settles after unmount', async outcome => {
    const onAuth = vi.fn();
    const onDone = vi.fn();
    const { hook, unmount } = mountStrict(onAuth);
    const pending = deferred<string>();
    let settled: Promise<boolean> | undefined;
    act(() => { settled = hook().run(() => pending.promise, onDone); });
    expect(screen.getByText(/^busy\|/)).toBeInTheDocument();
    unmount();
    if (outcome === 'success') pending.resolve('late');
    else pending.reject(outcome === 'auth' ? new ApiError('UNAUTHORIZED', 401) : new ApiError('INTERNAL', 500));
    const ok = await settled;
    // The server may have processed it, but the unmounted view must not apply the stale result.
    expect(ok).toBe(outcome === 'success');
    expect(onDone).not.toHaveBeenCalled();
    expect(onAuth).not.toHaveBeenCalled();
  });
});
