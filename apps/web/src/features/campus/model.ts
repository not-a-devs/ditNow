// Pure helpers shared by campus panels. Mirrors server limits; the server stays authoritative.
import { ApiError } from "../../lib/api";
import type { Audience, CampusErrorView, NoticeStatus, SourceKind } from "./types";

export const MESSAGE_MAX_LENGTH = 2000;

export function newClientNonce(): string {
  return `web-${crypto.randomUUID()}`;
}

/** One send intent: the exact (trimmed) body and the idempotency key issued for it. */
export interface PendingSend {
  body: string;
  nonce: string;
}

/** Reuse the key only for the identical body; any edit is a new intent with a new key. */
export function intentFor(pending: PendingSend | null, body: string, makeNonce = newClientNonce): PendingSend {
  return pending && pending.body === body ? pending : { body, nonce: makeNonce() };
}

/**
 * True when the server may already have stored the message (no definitive 4xx answer).
 * Retrying the same body then reuses the same key, so the server replays instead of duplicating.
 */
export function isUncertainSendFailure(error: unknown): boolean {
  if (!(error instanceof ApiError)) return true;
  return error.status === 0 || error.status >= 500 || error.code === "INVALID_RESPONSE";
}

/** Keep the intent after a failure unless the server said this key belongs to other content. */
export function intentAfterFailure(pending: PendingSend, error: unknown): PendingSend | null {
  return error instanceof ApiError && error.code === "CONFLICT" ? null : pending;
}

const SOURCE_URL_MAX_LENGTH = 2048;

/** Absolute http(s) URL with a host and no credentials, else null. Mirrors the server rule. */
export function safeSourceUrl(value: string | null | undefined): string | null {
  if (!value || value.length > SOURCE_URL_MAX_LENGTH || /[\s\u0000-\u001f\u007f-\u009f]/.test(value)) return null;
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return null;
  }
  if ((url.protocol !== "https:" && url.protocol !== "http:") || !url.hostname || url.username || url.password) {
    return null;
  }
  return url.href;
}

export interface Citation {
  kind: SourceKind;
  url: string | null;
  checkedAt: string | null;
}

/**
 * Defense in depth over the server's normalization: an "official" record without a safe link
 * and a valid check time is shown as UNKNOWN, and non-official records never get a link.
 */
export function citationOf(record: { source_kind: SourceKind; source_url: string | null; checked_at: string | null }): Citation {
  if (record.source_kind === "OFFICIAL_PUBLIC") {
    const url = safeSourceUrl(record.source_url);
    const checked = record.checked_at && !Number.isNaN(Date.parse(record.checked_at)) ? record.checked_at : null;
    if (url && checked) return { kind: "OFFICIAL_PUBLIC", url, checkedAt: checked };
    return { kind: "UNKNOWN", url: null, checkedAt: null };
  }
  return { kind: record.source_kind === "DEMO" ? "DEMO" : "UNKNOWN", url: null, checkedAt: null };
}

export function validateMessage(body: string): string | null {
  const text = body.trim();
  if (!text) return "메시지를 입력하세요.";
  if (text.length > MESSAGE_MAX_LENGTH) return `메시지는 ${MESSAGE_MAX_LENGTH}자 이하로 입력하세요.`;
  return null;
}

export function toErrorView(error: unknown): CampusErrorView {
  if (error instanceof ApiError) {
    const requestId = error.requestId;
    switch (error.code) {
      case "UNAVAILABLE":
        return {
          title: "서버 연결 준비 중",
          detail: "학과 채팅·공지·학사 API가 아직 인증/DB와 연결되지 않았습니다.",
          retryable: true,
          requestId,
        };
      case "UNAUTHORIZED":
        return { title: "로그인이 필요합니다", detail: "다시 로그인한 뒤 시도하세요.", retryable: false, requestId };
      case "FORBIDDEN":
        return {
          title: "접근할 수 없습니다",
          detail: "현재 소속 학과·학년 범위가 아닙니다.",
          retryable: false,
          requestId,
        };
      case "NOT_FOUND":
        return { title: "찾을 수 없습니다", detail: "삭제되었거나 볼 수 없는 항목입니다.", retryable: false, requestId };
      case "CONFLICT":
        return { title: "상태가 변경되었습니다", detail: "새로고침 후 다시 시도하세요.", retryable: true, requestId };
      case "VALIDATION":
        return { title: "입력값을 확인하세요", detail: "내용 또는 길이를 확인하세요.", retryable: false, requestId };
      case "RATE_LIMITED":
        return { title: "요청이 많습니다", detail: "잠시 후 다시 시도하세요.", retryable: true, requestId };
      case "NETWORK":
      case "CANCELLED":
        return { ...NETWORK_ERROR, requestId };
      default:
        return { title: "요청을 처리하지 못했습니다", detail: "잠시 후 다시 시도하세요.", retryable: true, requestId };
    }
  }
  return { ...NETWORK_ERROR };
}

const NETWORK_ERROR: CampusErrorView = {
  title: "네트워크 오류",
  detail: "서버에 연결하지 못했습니다. 연결 상태를 확인하세요.",
  retryable: true,
};

export function audienceLabel(audience: Audience): string {
  if (audience.type === "SCHOOL") return "전체";
  if (audience.type === "DEPARTMENT") return "학과 전체";
  return `학과 ${audience.grade}학년`;
}

export const NOTICE_STATUS_LABEL: Record<NoticeStatus, string> = {
  DRAFT: "초안",
  PUBLISHED: "게시",
  ARCHIVED: "보관됨",
};

export const SOURCE_LABEL: Record<SourceKind, string> = {
  DEMO: "가상 시연 데이터",
  OFFICIAL_PUBLIC: "공개 자료 스냅샷",
  UNKNOWN: "출처 미확인",
};

export function formatDateTime(iso: string): string {
  const value = new Date(iso);
  return Number.isNaN(value.getTime())
    ? iso
    : value.toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}
