import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from './data/api';
import { subscribe } from './data/store';

export interface ApiState<T> {
  data: T | undefined;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
}

function toApiError(e: unknown): ApiError {
  if (e instanceof ApiError) return e;
  return new ApiError('CONFLICT', '일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.');
}

/**
 * 조회 훅. 저장소가 바뀌면(같은 탭 또는 다른 탭) 자동으로 다시 불러온다 → 채팅 실시간 반영.
 * 재조회 중에는 이전 데이터를 유지해 화면이 깜빡이지 않게 한다.
 */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[]): ApiState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fetcher, deps);

  const load = useCallback(
    (silent: boolean) => {
      const id = ++seq.current;
      if (!silent) setLoading(true);
      run()
        .then((d) => {
          if (id !== seq.current) return;
          setData(d);
          setError(null);
        })
        .catch((e) => {
          if (id !== seq.current) return;
          setError(toApiError(e));
        })
        .finally(() => {
          if (id === seq.current) setLoading(false);
        });
    },
    [run],
  );

  useEffect(() => {
    setData(undefined);
    load(false);
    return subscribe(() => load(true));
  }, [load]);

  return { data, error, loading, reload: () => load(false) };
}

/**
 * 변경 요청 훅 — 중복 제출 방지(pending 중 재호출 무시)와 필드 오류 수집.
 * 실패하면 undefined, 성공하면 결과를 반환한다(결과가 없는 API는 true로 정규화).
 */
export function useMutation<A extends unknown[], R>(fn: (...args: A) => Promise<R>) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const busy = useRef(false);

  const mutate = useCallback(
    async (...args: A): Promise<(R extends void ? true : R) | undefined> => {
      if (busy.current) return undefined;
      busy.current = true;
      setPending(true);
      setError(null);
      try {
        const result = await fn(...args);
        return (result === undefined ? true : result) as R extends void ? true : R;
      } catch (e) {
        setError(toApiError(e));
        return undefined;
      } finally {
        busy.current = false;
        setPending(false);
      }
    },
    [fn],
  );

  return { mutate, pending, error, fieldErrors: error?.fieldErrors ?? {}, clearError: () => setError(null) };
}
