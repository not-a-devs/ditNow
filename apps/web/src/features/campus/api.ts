// Campus API client over the shared src/lib/api.ts: requestData<T>(path, init?) resolves `path`
// against VITE_API_BASE_URL (default /api/v1), returns success.data and throws
// ApiError(code/status/requestId).
import { requestData } from "../../lib/api";
import type {
  AcademicEventList,
  AcademicTerm,
  Channel,
  MessageList,
  MessageSend,
  Notice,
} from "./types";

// Paths are relative to the shared base. requestData already prefixes /api/v1, so adding it
// here produced /api/v1/api/v1/... (see api.test.ts).
const BASE = "";

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
