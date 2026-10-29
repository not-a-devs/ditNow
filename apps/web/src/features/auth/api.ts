import { ApiError, requestData, resolveApiUrl } from '../../lib/api';

export interface LoginCredentials { student_id: string; password: string }
export interface DemoLoginSession {
  token: string;
  token_type: 'Bearer';
  student_id: string;
  name: string;
  record_source: 'DEMO';
}

const codepoints = (value: unknown, max: number): value is string =>
  typeof value === 'string' && value.length <= max * 2
  && value.trim().length > 0 && Array.from(value).length <= max;
const object = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === 'object' && !Array.isArray(value);

export function isDemoLoginSession(value: unknown): value is DemoLoginSession {
  return object(value)
    && Object.keys(value).every(key => ['token', 'token_type', 'student_id', 'name', 'record_source'].includes(key))
    && typeof value.token === 'string' && value.token.length <= 4096
    && /^[A-Za-z0-9._~+/-]+={0,2}$/.test(value.token)
    && value.token_type === 'Bearer' && value.record_source === 'DEMO'
    && codepoints(value.student_id, 20) && codepoints(value.name, 200);
}

export function validateCredentials(input: LoginCredentials): string | null {
  if (!codepoints(input.student_id, 20)) return '학번을 1~20자로 입력해 주세요.';
  // Password whitespace is significant; do not trim or normalize credentials.
  if (typeof input.password !== 'string' || !input.password.length || input.password.length > 128
    || Array.from(input.password).length > 64) return '비밀번호를 1~64자로 입력해 주세요.';
  return null;
}

function requireSecureTransport(path: string) {
  const url = new URL(resolveApiUrl(path));
  const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && loopback)) {
    throw new ApiError('SECURE_TRANSPORT_REQUIRED', 0);
  }
}

export async function login(input: LoginCredentials, signal?: AbortSignal): Promise<DemoLoginSession> {
  if (validateCredentials(input)) throw new ApiError('VALIDATION', 400);
  requireSecureTransport('/auth/login');
  const value = await requestData<unknown>('/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ student_id: input.student_id, password: input.password }),
    signal, cache: 'no-store', credentials: 'omit', redirect: 'error', referrerPolicy: 'no-referrer',
  });
  if (!isDemoLoginSession(value) || value.student_id !== input.student_id) {
    throw new ApiError('INVALID_RESPONSE', 200);
  }
  return value;
}

export async function logout(token: string, signal?: AbortSignal): Promise<void> {
  if (typeof token !== 'string' || token.length > 4096 || !/^[A-Za-z0-9._~+/-]+={0,2}$/.test(token)) {
    throw new ApiError('INVALID_RESPONSE', 0);
  }
  requireSecureTransport('/auth/logout');
  const value = await requestData<unknown>('/auth/logout', {
    method: 'POST', headers: { Authorization: `Bearer ${token}` }, signal,
    cache: 'no-store', credentials: 'omit', redirect: 'error', referrerPolicy: 'no-referrer',
  });
  if (!object(value) || Object.keys(value).length !== 1 || value.status !== 'ok') {
    throw new ApiError('INVALID_RESPONSE', 200);
  }
}
