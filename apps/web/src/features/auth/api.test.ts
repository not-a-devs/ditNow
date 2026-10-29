import { afterEach, describe, expect, it, vi } from 'vitest';
import * as transport from '../../lib/api';
import { isDemoLoginSession, login, logout, validateCredentials } from './api';

const session = { token: 'fictional-token-for-test', token_type: 'Bearer', student_id: 'fictional-id', name: '가상 학생', record_source: 'DEMO' };
function response(data: unknown, status = 200) {
  return new Response(JSON.stringify({ data }), { status, headers: { 'Content-Type': 'application/json' } });
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('학번 로그인 전송 계약', () => {
  it('기존 API에 정확한 필드만 POST하고 브라우저 쿠키·캐시·리다이렉트를 사용하지 않는다', async () => {
    const fetch = vi.fn().mockResolvedValue(response(session)); vi.stubGlobal('fetch', fetch);
    const signal = new AbortController().signal;
    expect(await login({ student_id: 'fictional-id', password: '  fictional-password  ' }, signal)).toEqual(session);
    expect(fetch.mock.calls[0][0]).toBe(transport.resolveApiUrl('/auth/login'));
    const init = fetch.mock.calls[0][1];
    expect(JSON.parse(init.body)).toEqual({ student_id: 'fictional-id', password: '  fictional-password  ' });
    expect(init).toMatchObject({ method: 'POST', credentials: 'omit', cache: 'no-store', redirect: 'error', referrerPolicy: 'no-referrer' });
    expect(init.headers).toEqual({ 'Content-Type': 'application/json' });
    expect(fetch.mock.calls[0][0]).not.toContain('fictional-password');
  });
  it('가상 출처·Bearer·범위·예상하지 않은 권한 필드·헤더 개행을 검사한다', () => {
    expect(isDemoLoginSession(session)).toBe(true);
    for (const changed of [{ record_source: 'OFFICIAL' }, { token_type: 'Cookie' }, { roles: ['admin'] }, { token: 'token\r\nsecret' }, { token: '' }, { student_id: 'a'.repeat(21) }, { name: '' }]) {
      expect(isDemoLoginSession({ ...session, ...changed })).toBe(false);
    }
  });
  it('다른 학번 응답과 가상 표시가 없는 응답은 콜백에 전달할 수 없다', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response({ ...session, student_id: 'other' })).mockResolvedValueOnce(response({ ...session, record_source: undefined })));
    await expect(login({ student_id: 'fictional-id', password: 'pw' })).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    await expect(login({ student_id: 'fictional-id', password: 'pw' })).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  });
  it('문자 수 경계와 비밀번호의 유효 공백을 보존하고 잘못된 입력은 전송하지 않는다', async () => {
    expect(validateCredentials({ student_id: '가'.repeat(20), password: '🙂'.repeat(64) })).toBe(null);
    expect(validateCredentials({ student_id: 'id', password: ' ' })).toBe(null);
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    for (const input of [{ student_id: '', password: 'pw' }, { student_id: 'a'.repeat(21), password: 'pw' }, { student_id: 'id', password: '🙂'.repeat(65) }]) {
      await expect(login(input)).rejects.toMatchObject({ code: 'VALIDATION' });
    }
    expect(fetch).not.toHaveBeenCalled();
  });
  it('원격 평문 HTTP로는 자격 정보를 보내지 않는다', async () => {
    vi.spyOn(transport, 'resolveApiUrl').mockReturnValue('http://example.invalid/api/v1/auth/login');
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    await expect(login({ student_id: 'fictional-id', password: 'pw' })).rejects.toMatchObject({ code: 'SECURE_TRANSPORT_REQUIRED' });
    expect(fetch).not.toHaveBeenCalled();
  });
  it('로그아웃 토큰은 Authorization에만 넣고 확인되지 않은 응답은 거부한다', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(response({ status: 'ok' })).mockResolvedValueOnce(response({ status: 'unknown' }));
    vi.stubGlobal('fetch', fetch);
    await logout(session.token);
    expect(fetch.mock.calls[0][0]).toBe(transport.resolveApiUrl('/auth/logout'));
    expect(fetch.mock.calls[0][0]).not.toContain(session.token);
    expect(fetch.mock.calls[0][1]).toMatchObject({ headers: { Authorization: `Bearer ${session.token}` }, credentials: 'omit', cache: 'no-store', redirect: 'error' });
    expect(fetch.mock.calls[0][1].body).toBeUndefined();
    await expect(logout(session.token)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  });
  it('실패 응답의 원문·비밀값을 오류 메시지로 사용하지 않는다', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 'UNAUTHORIZED', message: 'private-password-secret' }), { status: 401 })));
    await expect(login({ student_id: 'fictional-id', password: 'pw' })).rejects.toMatchObject({ code: 'UNAUTHORIZED', message: '로그인이 필요한 기능입니다.' });
  });
});
