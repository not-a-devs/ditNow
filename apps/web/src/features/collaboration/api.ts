// Uses the shared client in ../../lib/api: requestData<T> resolves paths against the API base
// (default `/api/v1`) itself, so paths here are relative to that base and must not repeat it.
import { ApiError, requestData } from "../../lib/api";
import {
  ensure,
  isBookmark,
  isBookmarkState,
  isComment,
  isDeleted,
  isGroup,
  isJoinRequest,
  isMembership,
  isPostSummary,
  isReport,
  isSpacePost,
  pageOf,
} from "./guards";
import type { GroupInput, GroupKind, ReportReason, ReportTargetType } from "./types";

const id = encodeURIComponent;

const json = (method: string, body: unknown, headers: Record<string, string> = {}): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json", ...headers },
  body: JSON.stringify(body),
});

// Create POSTs require a key; an unchanged retry reuses it so the server replays, not duplicates.
const created = (body: unknown, key: string) => json("POST", body, { "Idempotency-Key": key });

const get = async <T,>(path: string, check: (value: unknown) => T) => check(await requestData<unknown>(path));
const send = async <T,>(path: string, init: RequestInit, check: (value: unknown) => T) =>
  check(await requestData<unknown>(path, init));

const query = (params: Record<string, string | undefined>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value) search.set(key, value);
  return search.toString();
};

export const collaborationApi = {
  searchPosts: (q: string) =>
    get(`/search/anonymous-posts?${query({ q, limit: "20" })}`, ensure(pageOf(isPostSummary))),
  listComments: (postId: string) =>
    get(`/anonymous-posts/${id(postId)}/comments?limit=50`, ensure(pageOf(isComment))),
  createComment: (postId: string, body: string, key: string) =>
    send(`/anonymous-posts/${id(postId)}/comments`, created({ body }, key), ensure(isComment)),
  deleteComment: (postId: string, commentId: string, revision: number) =>
    send(
      `/anonymous-posts/${id(postId)}/comments/${id(commentId)}?revision=${revision}`,
      { method: "DELETE" },
      ensure(isDeleted),
    ),
  listBookmarks: () => get("/me/bookmarks?limit=50", ensure(pageOf(isBookmark))),
  addBookmark: (postId: string) =>
    send(`/me/bookmarks/${id(postId)}`, { method: "PUT" }, ensure(isBookmarkState)),
  removeBookmark: (postId: string) =>
    send(`/me/bookmarks/${id(postId)}`, { method: "DELETE" }, ensure(isBookmarkState)),
  createReport: (target_type: ReportTargetType, target_id: string, reason: ReportReason, key: string) =>
    send("/reports", created({ target_type, target_id, reason }, key), ensure(isReport)),
  listReports: () => get("/me/reports?limit=50", ensure(pageOf(isReport))),
  listGroups: (kind?: GroupKind, q?: string) =>
    get(`/groups?${query({ kind, q, limit: "20" })}`, ensure(pageOf(isGroup))),
  getGroup: (groupId: string) => get(`/groups/${id(groupId)}`, ensure(isGroup)),
  createGroup: (input: GroupInput, key: string) => send("/groups", created(input, key), ensure(isGroup)),
  requestJoin: (groupId: string, key: string) =>
    send(`/groups/${id(groupId)}/join-requests`, { method: "POST", headers: { "Idempotency-Key": key } }, ensure(isMembership)),
  listJoinRequests: (groupId: string) =>
    get(`/groups/${id(groupId)}/join-requests?limit=50`, ensure(pageOf(isJoinRequest))),
  decideJoin: (groupId: string, membershipId: string, decision: "approve" | "reject", revision: number) =>
    send(
      `/groups/${id(groupId)}/join-requests/${id(membershipId)}/decision`,
      json("POST", { decision, revision }),
      ensure(isJoinRequest),
    ),
  leaveGroup: (groupId: string, revision: number) =>
    send(`/groups/${id(groupId)}/membership/leave`, json("POST", { revision }), ensure(isMembership)),
  listSpacePosts: (groupId: string) =>
    get(`/groups/${id(groupId)}/space/posts?limit=50`, ensure(pageOf(isSpacePost))),
  createSpacePost: (groupId: string, body: string, key: string) =>
    send(`/groups/${id(groupId)}/space/posts`, created({ body }, key), ensure(isSpacePost)),
  deleteSpacePost: (groupId: string, postId: string, revision: number) =>
    send(`/groups/${id(groupId)}/space/posts/${id(postId)}?revision=${revision}`, { method: "DELETE" }, ensure(isDeleted)),
};

/**
 * One key per logical submission. An unchanged retry after a failure keeps the key, any change
 * to the intent rotates it, and a confirmed success (reset) starts a new one.
 */
export function createKeyTracker(generate: () => string = () => crypto.randomUUID()) {
  let last: { intent: string; key: string } | null = null;
  return {
    keyFor(intent: unknown): string {
      const serialized = JSON.stringify(intent);
      if (last?.intent !== serialized) last = { intent: serialized, key: generate() };
      return last.key;
    },
    reset() {
      last = null;
    },
  };
}

export type IssueKind = "unavailable" | "unauthenticated" | "forbidden" | "error";

export interface Issue {
  kind: IssueKind;
  message: string;
  requestId?: string;
}

export const isAuthIssue = (issue: Issue) => issue.kind === "unauthenticated" || issue.kind === "forbidden";

// Fixed Korean messages only; server-provided text is never shown.
export function describeError(error: unknown): Issue {
  if (!(error instanceof ApiError)) return { kind: "unavailable", message: "서버에 연결할 수 없습니다. 연결 준비 중입니다." };
  const requestId = error.requestId;
  if (error.status === 401) return { kind: "unauthenticated", message: "로그인이 필요합니다." };
  if (error.status === 403) return { kind: "forbidden", message: "커뮤니티 참여 권한이 확인되지 않았습니다." };
  if (error.code === "INVALID_RESPONSE") return { kind: "error", message: "서버 응답 형식을 확인할 수 없습니다.", requestId };
  if (error.status === 0 || error.status === 503)
    return { kind: "unavailable", message: "협업 서버가 아직 연결되지 않았습니다. 연결 준비 중입니다.", requestId };
  if (error.status === 404) return { kind: "error", message: "대상을 찾을 수 없거나 접근할 수 없습니다.", requestId };
  if (error.status === 409) return { kind: "error", message: "현재 상태와 충돌했습니다. 새로 불러온 뒤 다시 확인하세요.", requestId };
  if (error.status === 400) return { kind: "error", message: "입력값을 확인하세요.", requestId };
  if (error.status === 429) return { kind: "error", message: "요청이 많습니다. 잠시 후 다시 시도하세요.", requestId };
  return { kind: "error", message: "요청을 처리하지 못했습니다.", requestId };
}
