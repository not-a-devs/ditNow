// Uses the shared client in ../../lib/api: requestData<T> resolves paths against the API base
// (default `/api/v1`) itself, so paths here must not repeat it.
import { ApiError, requestData } from "../../lib/api";
import type {
  ChannelInput,
  ChannelPage,
  CreatedChannel,
  CreatedRequest,
  FreeChannel,
  LeaveReceipt,
  MembershipResult,
  OfficialRequest,
  RequestPage,
} from "./types";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ISO = (value: unknown) => typeof value === "string" && !Number.isNaN(Date.parse(value));
const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const isCursor = (value: unknown) => value === null || (Number.isInteger(value) && (value as number) >= 1);

export const isUuid = (value: unknown): value is string => typeof value === "string" && UUID.test(value);

export function isFreeChannel(value: unknown): value is FreeChannel {
  if (!isRecord(value)) return false;
  const grade = value.grade;
  return (
    isUuid(value.id) &&
    isUuid(value.department_id) &&
    (grade === null || (Number.isInteger(grade) && (grade as number) >= 1 && (grade as number) <= 6)) &&
    value.kind === "FREE" &&
    // A response claiming official status is invalid: no approval flow exists in this pass.
    value.is_official === false &&
    typeof value.name === "string" &&
    typeof value.description === "string" &&
    (value.status === "ACTIVE" || value.status === "ARCHIVED") &&
    Number.isInteger(value.revision) &&
    Number.isInteger(value.member_count) &&
    (value.my_role === null || value.my_role === "OWNER" || value.my_role === "MEMBER") &&
    ISO(value.created_at) &&
    (value.archived_at === null || ISO(value.archived_at))
  );
}

export function isOfficialRequest(value: unknown): value is OfficialRequest {
  return (
    isRecord(value) &&
    isUuid(value.id) &&
    isUuid(value.channel_id) &&
    (value.status === "PENDING" || value.status === "CANCELLED") &&
    value.review_state === "BLOCKED_APPROVER_POLICY" &&
    typeof value.reason === "string" &&
    Number.isInteger(value.revision) &&
    ISO(value.created_at) &&
    ISO(value.updated_at)
  );
}

function check<T>(ok: (value: unknown) => boolean, value: unknown): T {
  if (!ok(value)) throw new ApiError("INVALID_RESPONSE", 200);
  return value as T;
}

const isChannelPage = (v: unknown) =>
  isRecord(v) && Array.isArray(v.items) && v.items.every(isFreeChannel) && isCursor(v.next_before);
const isRequestPage = (v: unknown) =>
  isRecord(v) && Array.isArray(v.items) && v.items.every(isOfficialRequest) && isCursor(v.next_before);
const isMembership = (v: unknown) => isRecord(v) && isFreeChannel(v.channel) && typeof v.changed === "boolean";
const isLeaveReceipt = (v: unknown) => isRecord(v) && Object.keys(v).length === 3
  && isUuid(v.channel_id) && typeof v.changed === "boolean" && v.membership === "ABSENT";
const isCreatedChannel = (v: unknown) => isRecord(v) && isFreeChannel(v.channel) && typeof v.replayed === "boolean";
const isCreatedRequest = (v: unknown) =>
  isRecord(v) && isOfficialRequest(v.request) && typeof v.replayed === "boolean";

// IDs become path segments only when they are UUIDs; anything else is refused before a request,
// so "../" or look-alike Unicode can never reach another route.
const seg = (value: string) => {
  if (!isUuid(value)) throw new ApiError("INVALID_RESPONSE", 0);
  return value;
};

const cursor = (before: number | null | undefined, limit: number) =>
  `limit=${limit}${before ? `&before=${before}` : ""}`;

const json = (method: string, body: unknown, headers: Record<string, string> = {}): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json", ...headers },
  body: JSON.stringify(body),
});

// Paths are built lazily so an invalid ID rejects the returned promise instead of throwing.
async function call<T>(path: () => string, ok: (v: unknown) => boolean, init: RequestInit = {}): Promise<T> {
  return check<T>(ok, await requestData<unknown>(path(), init));
}

export const PAGE_SIZE = 20;

export const channelsApi = {
  listDepartment: (departmentId: string, before?: number | null, signal?: AbortSignal) =>
    call<ChannelPage>(
      () => `/departments/${seg(departmentId)}/free-channels?${cursor(before, PAGE_SIZE)}`,
      isChannelPage,
      signal ? { signal } : {},
    ),
  listMine: (before?: number | null, signal?: AbortSignal) =>
    call<ChannelPage>(() => `/me/free-channels?${cursor(before, PAGE_SIZE)}`, isChannelPage, signal ? { signal } : {}),
  create: (input: ChannelInput, key: string, signal?: AbortSignal) =>
    call<CreatedChannel>(() => "/free-channels", isCreatedChannel, { ...json("POST", input, { "Idempotency-Key": key }), signal }),
  update: (id: string, name: string, description: string, expectedRevision: number, signal?: AbortSignal) =>
    call<FreeChannel>(
      () => `/free-channels/${seg(id)}`,
      isFreeChannel,
      { ...json("PATCH", { name, description, expected_revision: expectedRevision }), signal },
    ),
  archive: (id: string, expectedRevision: number, signal?: AbortSignal) =>
    call<FreeChannel>(
      () => `/free-channels/${seg(id)}/archive`,
      isFreeChannel,
      { ...json("POST", { expected_revision: expectedRevision }), signal },
    ),
  join: (id: string, signal?: AbortSignal) => call<MembershipResult>(() => `/free-channels/${seg(id)}/join`, isMembership, { method: "POST", signal }),
  leave: async (id: string, signal?: AbortSignal) => {
    const receipt = await call<LeaveReceipt>(() => `/free-channels/${seg(id)}/leave`, isLeaveReceipt, { method: "POST", signal });
    if (receipt.channel_id !== id) throw new ApiError("INVALID_RESPONSE", 200);
    return receipt;
  },
  requestOfficial: (id: string, reason: string, key: string, signal?: AbortSignal) =>
    call<CreatedRequest>(
      () => `/free-channels/${seg(id)}/official-requests`,
      isCreatedRequest,
      { ...json("POST", { reason }, { "Idempotency-Key": key }), signal },
    ),
  myRequests: (signal?: AbortSignal) =>
    call<RequestPage>(() => `/me/official-channel-requests?${cursor(null, PAGE_SIZE)}`, isRequestPage, signal ? { signal } : {}),
};

export const NAME_MAX_LENGTH = 40;
export const DESCRIPTION_MAX_LENGTH = 500;
export const REASON_MIN_LENGTH = 10;
export const REASON_MAX_LENGTH = 1000;

// Code points after NFC, like the server. The server re-validates and stays authoritative.
const length = (text: string) => [...text.normalize("NFC")].length;
// Control and invisible format characters (bidi overrides, zero-width) except ZWJ in emoji.
const FORBIDDEN = /[\p{Cc}\p{Cs}]|(?!‍)\p{Cf}/u;

export function validateName(name: string): string | null {
  const text = name.trim();
  if (!text) return "채널 이름을 입력하세요.";
  if (length(text) > NAME_MAX_LENGTH) return `채널 이름은 ${NAME_MAX_LENGTH}자 이하로 입력하세요.`;
  if (FORBIDDEN.test(text)) return "줄바꿈·제어·보이지 않는 문자는 쓸 수 없습니다.";
  return null;
}

export function validateDescription(text: string): string | null {
  if (length(text.trim()) > DESCRIPTION_MAX_LENGTH) return `설명은 ${DESCRIPTION_MAX_LENGTH}자 이하로 입력하세요.`;
  if (FORBIDDEN.test(text.replace(/[\n\t]/g, ""))) return "제어·보이지 않는 문자는 쓸 수 없습니다.";
  return null;
}

export function validateReason(reason: string): string | null {
  const n = length(reason.trim());
  if (n < REASON_MIN_LENGTH) return `신청 사유를 ${REASON_MIN_LENGTH}자 이상 입력하세요.`;
  if (n > REASON_MAX_LENGTH) return `신청 사유는 ${REASON_MAX_LENGTH}자 이하로 입력하세요.`;
  if (FORBIDDEN.test(reason.replace(/[\n\t]/g, ""))) return "제어·보이지 않는 문자는 쓸 수 없습니다.";
  return null;
}
