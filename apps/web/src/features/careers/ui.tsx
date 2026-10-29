// Shared presentational helpers for the careers module. All text is rendered as React text
// nodes (escaped); links are only rendered after safeHref() accepted an https URL.
import { ApiError } from '../../lib/api';
import { safeHref } from './guards';
import type { Provenance } from './types';

export type Load<T> =
  | { state: 'loading' }
  | { state: 'error'; message: string; requestId?: string }
  | { state: 'ready'; data: T };

export type PrivateArea = 'profile' | 'applications' | 'employer';

export const AREA_LABEL: Record<PrivateArea, string> = {
  profile: '가상 진로·이력 요약',
  applications: '프로그램 가상 신청',
  employer: '기업 채용의뢰 초안',
};

/** 401/403 are handled by the parent: the panel's personal data is removed, not just hidden. */
export function authCode(error: unknown): 'UNAUTHORIZED' | 'FORBIDDEN' | null {
  if (!(error instanceof ApiError)) return null;
  if (error.status === 401) return 'UNAUTHORIZED';
  if (error.status === 403) return 'FORBIDDEN';
  return null;
}

export function describeError(error: unknown): { message: string; requestId?: string } {
  if (!(error instanceof ApiError)) return { message: '서버에 연결할 수 없습니다. 네트워크 상태를 확인하세요.' };
  const requestId = error.requestId;
  if (error.status === 0 && (error.code === 'NETWORK' || error.code === 'CANCELLED'))
    return { message: '서버에 연결할 수 없습니다. 네트워크 상태를 확인하세요.' };
  if (error.code === 'INVALID_RESPONSE') return { message: '서버 응답 형식이 올바르지 않아 표시하지 않았습니다.', requestId };
  if (error.status === 503) return { message: '서버 연결 준비 중입니다. 아직 이용할 수 없습니다.', requestId };
  if (error.status === 404) return { message: '찾을 수 없거나 접근할 수 없는 항목입니다.', requestId };
  if (error.status === 409) return { message: '현재 상태와 충돌합니다. 최신 내용을 다시 확인하세요.', requestId };
  if (error.status === 400) return { message: '입력값을 확인하세요. 실명·연락처·링크·파일은 입력할 수 없습니다.', requestId };
  return { message: '요청을 처리하지 못했습니다. 잠시 후 다시 시도하세요.', requestId };
}

export function ErrorBox({ message, requestId, onRetry }: { message: string; requestId?: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
      <p>{message}</p>
      {requestId && <p className="mt-1 text-xs text-red-600">요청 ID: {requestId}</p>}
      {onRetry && (
        <button type="button" onClick={onRetry} className="mt-2 rounded border border-red-300 px-2 py-1 text-xs">
          다시 시도
        </button>
      )}
    </div>
  );
}

export function Loading({ label }: { label: string }) {
  return <p className="text-sm text-slate-500" aria-busy="true">{label}</p>;
}

export function formatDate(value: string | null): string {
  if (!value) return '기한 정보 없음';
  return new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Seoul' }).format(new Date(value));
}

export function ProvenanceBadge({ kind, checkedAt }: { kind: Provenance; checkedAt: string | null }) {
  if (kind === 'OFFICIAL_PUBLIC')
    return <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-800">공개 원문 · 확인 {formatDate(checkedAt)}</span>;
  if (kind === 'DEMO') return <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800">DEMO 가상 자료</span>;
  return <span className="rounded bg-orange-100 px-1.5 py-0.5 text-xs text-orange-800">출처 미확인 — 원문 확인 필요</span>;
}

export function SourceLink({ url, label = '원문 열기' }: { url: string | null; label?: string }) {
  const href = safeHref(url);
  if (!href) return <span className="text-xs text-slate-500">원문 링크 없음</span>;
  return <a className="text-xs text-sky-700 underline" href={href} target="_blank" rel="noopener noreferrer">{label}</a>;
}
