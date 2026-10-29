// Campus API client. Depends on the shared src/lib/api.ts (being written on another branch):
// requestData<T>(path, init?) returns success.data and throws ApiError(code/status/requestId).
import { requestData } from "../../lib/api";
import type {
  AcademicEventList,
  AcademicTerm,
  Channel,
  MessageList,
  MessageSend,
  Notice,
} from "./types";

// Assumption: root mounts the campus router under /api/v1 and requestData takes absolute paths.
const BASE = "/api/v1";

const enc = encodeURIComponent;

export function listDepartmentChannels(departmentId: string) {
  return requestData<{ items: Channel[] }>(`${BASE}/departments/${enc(departmentId)}/channels`);
}

export function listMessages(channelId: string, before?: number, limit = 50) {
  const query = new URLSearchParams({ limit: String(limit) });
  if (before !== undefined) query.set("before", String(before));
  return requestData<MessageList>(`${BASE}/channels/${enc(channelId)}/messages?${query}`);
}

export function sendMessage(channelId: string, body: string, clientNonce: string) {
  return requestData<MessageSend>(`${BASE}/channels/${enc(channelId)}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body, client_nonce: clientNonce }),
  });
}

export function listNotices(limit = 20) {
  return requestData<{ items: Notice[] }>(`${BASE}/notices?limit=${limit}`);
}

export function getNotice(noticeId: string) {
  return requestData<Notice>(`${BASE}/notices/${enc(noticeId)}`);
}

export function listTerms() {
  return requestData<{ items: AcademicTerm[] }>(`${BASE}/academic/terms`);
}

export function listTermEvents(termId: string) {
  return requestData<AcademicEventList>(`${BASE}/academic/terms/${enc(termId)}/events`);
}
