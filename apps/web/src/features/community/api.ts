// Uses the shared client in ../../lib/api: requestData<T> resolves paths against the API base
// (default `/api/v1`) itself, so paths here are relative to that base and must not repeat it.
import { ApiError, requestData } from "../../lib/api";
import type {
  AnonymousPost,
  AnonymousPostInput,
  Page,
  Recruitment,
  RecruitmentInput,
  RecruitmentUpdate,
} from "./types";

const BASE = "";

const json = (method: string, body: unknown, headers: Record<string, string> = {}): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json", ...headers },
  body: JSON.stringify(body),
});

// Create POSTs require a key; reuse it for an unchanged retry so the server replays, not duplicates.
const created = (body: unknown, idempotencyKey: string) =>
  json("POST", body, { "Idempotency-Key": idempotencyKey });

export const communityApi = {
  listPosts: (signal?: AbortSignal) => requestData<Page<AnonymousPost>>(`${BASE}/anonymous-posts?limit=20`, { signal }),
  createPost: (input: AnonymousPostInput, idempotencyKey: string) =>
    requestData<AnonymousPost>(`${BASE}/anonymous-posts`, created(input, idempotencyKey)),
  updatePost: (id: string, revision: number, input: Partial<AnonymousPostInput>) =>
    requestData<AnonymousPost>(
      `${BASE}/anonymous-posts/${encodeURIComponent(id)}`,
      json("PATCH", { revision, ...input }),
    ),
  deletePost: (id: string, revision: number) =>
    requestData<{ id: string; deleted: boolean }>(
      `${BASE}/anonymous-posts/${encodeURIComponent(id)}?revision=${revision}`,
      { method: "DELETE" },
    ),
  listRecruitments: (signal?: AbortSignal) => requestData<Page<Recruitment>>(`${BASE}/recruitments?limit=20`, { signal }),
  createRecruitment: (input: RecruitmentInput, idempotencyKey: string) =>
    requestData<Recruitment>(`${BASE}/recruitments`, created(input, idempotencyKey)),
  updateRecruitment: (id: string, revision: number, changes: RecruitmentUpdate) =>
    requestData<Recruitment>(
      `${BASE}/recruitments/${encodeURIComponent(id)}`,
      json("PATCH", { revision, ...changes }),
    ),
  cancelRecruitment: (id: string, revision: number) =>
    requestData<{ id: string; deleted: true }>(`${BASE}/recruitments/${encodeURIComponent(id)}?revision=${revision}`, { method: "DELETE" }),
  closeRecruitment: (id: string, revision: number) =>
    requestData<Recruitment>(
      `${BASE}/recruitments/${encodeURIComponent(id)}/close`,
      json("POST", { revision }),
    ),
};

// One key per logical submission: an unchanged retry after a failure keeps the key; any edit
// to the input, or a success (reset), starts a new one.
export function createKeyTracker(generate: () => string = () => crypto.randomUUID()) {
  let last: { body: string; key: string } | null = null;
  return {
    keyFor(input: unknown): string {
      const body = JSON.stringify(input);
      if (last?.body !== body) last = { body, key: generate() };
      return last.key;
    },
    reset() {
      last = null;
    },
  };
}

export type LoadIssue = "unavailable" | "unauthenticated" | "forbidden" | "error";

export interface IssueInfo {
  kind: LoadIssue;
  message: string;
  requestId?: string;
}

// 404/503/network mean the router is not mounted or auth/DB are not connected yet.
export function describeError(error: unknown): IssueInfo {
  if (error instanceof ApiError) {
    if (error.status === 401) return { kind: "unauthenticated", message: "로그인이 필요합니다." };
    if (error.status === 403)
      return { kind: "forbidden", message: "커뮤니티를 이용할 권한이 확인되지 않았습니다." };
    if (error.status === 0 || error.status === 404 || error.status === 503)
      return {
        kind: "unavailable",
        message: "커뮤니티 서버가 아직 연결되지 않았습니다. 연결 준비 중입니다.",
        requestId: error.requestId,
      };
    if (error.status === 409)
      return {
        kind: "error",
        message: "다른 변경과 충돌했습니다. 목록을 새로 불러온 뒤 다시 시도하세요.",
        requestId: error.requestId,
      };
    if (error.status === 429)
      return { kind: "error", message: error.message, requestId: error.requestId };
    if (error.status === 400)
      return { kind: "error", message: "입력값을 확인하세요.", requestId: error.requestId };
    return { kind: "error", message: "요청을 처리하지 못했습니다.", requestId: error.requestId };
  }
  return { kind: "unavailable", message: "서버에 연결할 수 없습니다. 연결 준비 중입니다." };
}
