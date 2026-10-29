// Pure helpers shared by campus panels. Mirrors server limits; the server stays authoritative.
import { ApiError } from "../../lib/api";
import type { Audience, CampusErrorView, NoticeStatus, SourceKind } from "./types";

export const MESSAGE_MAX_LENGTH = 2000;

export function newClientNonce(): string {
  return `web-${crypto.randomUUID()}`;
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
      default:
        return { title: "요청을 처리하지 못했습니다", detail: "잠시 후 다시 시도하세요.", retryable: true, requestId };
    }
  }
  return {
    title: "네트워크 오류",
    detail: "서버에 연결하지 못했습니다. 연결 상태를 확인하세요.",
    retryable: true,
  };
}

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
};

export function formatDateTime(iso: string): string {
  const value = new Date(iso);
  return Number.isNaN(value.getTime())
    ? iso
    : value.toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}
