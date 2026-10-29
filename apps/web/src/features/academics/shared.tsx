import { useEffect, useRef, useState, type ReactNode } from 'react';
import { isAuthFailure, messageOf } from './api';
import styles from './academics.module.css';

export type OnAuthFailure = (error: unknown) => void;

type LoadState<T> = { status: 'loading' } | { status: 'ready'; data: T } | { status: 'error'; message: string };

export function useLoader<T>(load: (signal: AbortSignal) => Promise<T>, deps: readonly unknown[], onAuth: OnAuthFailure) {
  const [state, setState] = useState<LoadState<T>>({ status: 'loading' });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setState({ status: 'loading' });
    load(controller.signal).then(
      data => { if (!controller.signal.aborted) setState({ status: 'ready', data }); },
      error => {
        if (controller.signal.aborted) return;
        if (isAuthFailure(error)) onAuth(error);
        setState({ status: 'error', message: messageOf(error) });
      },
    );
    return () => controller.abort();
  }, [...deps, tick]);
  return { state, reload: () => setTick(t => t + 1), replace: (data: T) => setState({ status: 'ready', data }) };
}

/** Runs one mutation at a time; reports success only after a guarded server response. */
export function useAction(onAuth: OnAuthFailure) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const mounted = useRef(true);
  useEffect(() => () => { mounted.current = false; }, []);
  async function run<T>(action: () => Promise<T>, onDone: (data: T) => void): Promise<boolean> {
    setBusy(true); setError('');
    try {
      const data = await action();
      if (mounted.current) onDone(data);
      return true;
    } catch (failure) {
      if (!mounted.current) return false;
      if (isAuthFailure(failure)) onAuth(failure);
      setError(messageOf(failure));
      return false;
    } finally { if (mounted.current) setBusy(false); }
  }
  return { busy, error, run, clearError: () => setError('') };
}

export function Loaded<T>({ state, reload, empty, children }: {
  state: LoadState<T>; reload: () => void; empty?: (data: T) => boolean; children: (data: T) => ReactNode;
}) {
  if (state.status === 'loading') return <p role="status" className={styles.muted}>불러오는 중…</p>;
  if (state.status === 'error') return <div role="alert" className={styles.alert}><p>{state.message}</p><button type="button" onClick={reload}>다시 시도</button></div>;
  if (empty?.(state.data)) return <p className={styles.muted}>표시할 시연 기록이 없습니다.</p>;
  return <>{children(state.data)}</>;
}

export const when = (value: string | null) => value ? new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' }).format(new Date(value)) + ' UTC' : '—';
export const Alert = ({ message }: { message: string }) => message ? <p role="alert" className={styles.alert}>{message}</p> : null;
