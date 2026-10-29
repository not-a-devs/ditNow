// Uses the shared client being written on another branch: requestData<T> returns success.data
// and throws ApiError(code/status/requestId). Not compiled in this branch (NOT_RUN).
import { ApiError, requestData } from "../../lib/api";
import type {
  AnonymousPost,
  AnonymousPostInput,
  Page,
  Recruitment,
  RecruitmentInput,
} from "./types";

const BASE = "/api/v1";

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const communityApi = {
  listPosts: () => requestData<Page<AnonymousPost>>(`${BASE}/anonymous-posts?limit=20`),
  createPost: (input: AnonymousPostInput) =>
    requestData<AnonymousPost>(`${BASE}/anonymous-posts`, json("POST", input)),
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
  listRecruitments: () => requestData<Page<Recruitment>>(`${BASE}/recruitments?limit=20`),
  createRecruitment: (input: RecruitmentInput) =>
    requestData<Recruitment>(`${BASE}/recruitments`, json("POST", input)),
  closeRecruitment: (id: string, revision: number) =>
    requestData<Recruitment>(
      `${BASE}/recruitments/${encodeURIComponent(id)}/close`,
      json("POST", { revision }),
    ),
};

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
    if (error.status === 404 || error.status === 503)
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
    if (error.status === 400)
      return { kind: "error", message: "입력값을 확인하세요.", requestId: error.requestId };
    return { kind: "error", message: "요청을 처리하지 못했습니다.", requestId: error.requestId };
  }
  return { kind: "unavailable", message: "서버에 연결할 수 없습니다. 연결 준비 중입니다." };
}
