const codes: Record<string, string> = {
  UNAUTHORIZED: '로그인이 필요한 기능입니다.',
  FORBIDDEN: '이 기능에 접근할 권한이 없습니다.',
  NOT_FOUND: '요청한 내용을 찾을 수 없습니다.',
  CONFLICT: '내용이 변경되었습니다. 새로 확인해 주세요.',
  VALIDATION: '입력한 내용을 확인해 주세요.',
  RATE_LIMITED: '요청이 많습니다. 잠시 후 다시 시도해 주세요.',
};

export class ApiError extends Error {
  constructor(public readonly code: string, public readonly status: number, public readonly requestId?: string) {
    super(codes[code] ?? '서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.');
    this.name = 'ApiError';
  }
}

export function resolveApiUrl(path: string, configuredBase = import.meta.env.VITE_API_BASE_URL ?? ''): string {
  const origin = window.location.origin;
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('\\')
    || /%(?:2e|2f|5c)/i.test(path.split('?')[0])) {
    throw new ApiError('CONFIGURATION', 0);
  }
  let base: URL;
  try {
    base = new URL(configuredBase || '/api/v1', origin);
  } catch { throw new ApiError('CONFIGURATION', 0); }
  if (!['http:', 'https:'].includes(base.protocol) || base.username || base.password || base.search || base.hash) {
    throw new ApiError('CONFIGURATION', 0);
  }
  if (configuredBase && !/^https?:\/\//.test(configuredBase)) throw new ApiError('CONFIGURATION', 0);
  const prefix = base.pathname.replace(/\/$/, '') + '/';
  const target = new URL(path.slice(1), base.origin + prefix);
  if (target.origin !== base.origin || !target.pathname.startsWith(prefix) || target.hash) {
    throw new ApiError('CONFIGURATION', 0);
  }
  return target.href;
}

export async function requestData<T>(path: string, init: RequestInit = {}): Promise<T> {
  const url = resolveApiUrl(path);
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (init.signal?.aborted) abort();
  init.signal?.addEventListener('abort', abort, { once: true });
  const timer = setTimeout(abort, 10_000);
  try {
    const response = await fetch(url, { ...init, credentials: init.credentials ?? 'same-origin', signal: controller.signal });
    const body: unknown = await response.json().catch(() => null);
    const record = body && typeof body === 'object' ? body as Record<string, unknown> : null;
    const rawId = record?.request_id ?? response.headers.get('X-Request-ID');
    const requestId = typeof rawId === 'string' && /^[0-9a-f-]{36}$/i.test(rawId) ? rawId : undefined;
    if (!response.ok) {
      const code = typeof record?.code === 'string' && /^[A-Z_]{1,40}$/.test(record.code) ? record.code : 'UNAVAILABLE';
      throw new ApiError(code, response.status, requestId);
    }
    if (!record || !Object.hasOwn(record, 'data')) throw new ApiError('INVALID_RESPONSE', response.status, requestId);
    return record.data as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(controller.signal.aborted ? 'CANCELLED' : 'NETWORK', 0);
  } finally {
    clearTimeout(timer);
    init.signal?.removeEventListener('abort', abort);
  }
}
