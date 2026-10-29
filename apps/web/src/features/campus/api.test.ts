// Exercises the real shared requestData with a stubbed fetch, so the final URL is what the
// browser would actually request.
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../lib/api";
import {
  getNotice,
  listDepartmentChannels,
  listMessages,
  listNotices,
  listTermEvents,
  listTerms,
  sendMessage,
} from "./api";
import {
  citationOf,
  intentAfterFailure,
  intentFor,
  isUncertainSendFailure,
  safeSourceUrl,
} from "./model";

function stubOk(data: unknown = { items: [] }) {
  const fetch = vi.fn(
    async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({ data }), { status: 200 }),
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const urlOf = (fetch: ReturnType<typeof stubOk>, call = 0) => String(fetch.mock.calls[call][0]);

describe("campus API paths through the shared client", () => {
  const origin = window.location.origin;
  it.each([
    ["channels", () => listDepartmentChannels("dept-a"), "/api/v1/departments/dept-a/channels"],
    ["messages", () => listMessages("ch-1"), "/api/v1/channels/ch-1/messages?limit=50"],
    ["messages page", () => listMessages("ch-1", 7, 20), "/api/v1/channels/ch-1/messages?limit=20&before=7"],
    ["send", () => sendMessage("ch-1", "hi", "web-nonce-1"), "/api/v1/channels/ch-1/messages"],
    ["notices", () => listNotices(), "/api/v1/notices?limit=20"],
    ["notice", () => getNotice("n-1"), "/api/v1/notices/n-1"],
    ["terms", () => listTerms(), "/api/v1/academic/terms"],
    ["events", () => listTermEvents("t-1"), "/api/v1/academic/terms/t-1/events"],
  ])("%s has exactly one /api/v1 prefix", async (_name, call, path) => {
    const fetch = stubOk();
    await call();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(urlOf(fetch)).toBe(`${origin}${path}`);
    expect(urlOf(fetch)).not.toContain("/api/v1/api/v1");
  });

  it("uses a configured absolute API base exactly once", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1");
    const fetch = stubOk();
    await listNotices();
    expect(urlOf(fetch)).toBe("https://api.example.test/api/v1/notices?limit=20");
  });

  it("posts the body and idempotency key as JSON with same-origin credentials", async () => {
    const fetch = stubOk({ message: {}, replayed: false });
    await sendMessage("ch-1", "안녕", "web-nonce-1");
    const init = fetch.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
    expect(JSON.parse(String(init.body))).toEqual({ body: "안녕", client_nonce: "web-nonce-1" });
  });

  it.each(["../session", "a/../../b", "x?y=1#z"])("encodes ids so they cannot leave the API base: %s", async (id) => {
    const fetch = stubOk();
    await getNotice(id).catch((error: unknown) => expect(error).toBeInstanceOf(ApiError));
    for (const call of fetch.mock.calls) {
      const url = new URL(String(call[0]));
      expect(url.pathname.startsWith("/api/v1/notices/")).toBe(true);
      expect(url.search).toBe("");
    }
  });
});

describe("send intents", () => {
  let counter = 0;
  const make = () => `web-test-${++counter}`;

  it("reuses the key only for the identical body", () => {
    const first = intentFor(null, "hello", make);
    expect(intentFor(first, "hello", make)).toBe(first);
    const edited = intentFor(first, "hello!", make);
    expect(edited.nonce).not.toBe(first.nonce);
    expect(edited.body).toBe("hello!");
  });

  it.each([
    [new ApiError("NETWORK", 0), true],
    [new ApiError("CANCELLED", 0), true],
    [new ApiError("UNAVAILABLE", 503), true],
    [new ApiError("INTERNAL", 500), true],
    [new ApiError("INVALID_RESPONSE", 200), true],
    [new Error("boom"), true],
    [new ApiError("VALIDATION", 400), false],
    [new ApiError("FORBIDDEN", 403), false],
    [new ApiError("CONFLICT", 409), false],
  ])("classifies %o as uncertain=%s", (error, uncertain) => {
    expect(isUncertainSendFailure(error)).toBe(uncertain);
  });

  it("drops the intent only when the server says the key belongs to other content", () => {
    const intent = { body: "a", nonce: "web-x" };
    expect(intentAfterFailure(intent, new ApiError("NETWORK", 0))).toBe(intent);
    expect(intentAfterFailure(intent, new ApiError("VALIDATION", 400))).toBe(intent);
    expect(intentAfterFailure(intent, new ApiError("CONFLICT", 409))).toBeNull();
  });
});

describe("source allowlist", () => {
  it.each(["https://www.example.ac.kr/cal?x=1", "http://example.ac.kr/"])("accepts %s", (url) => {
    expect(safeSourceUrl(url)).toBe(url);
  });

  it.each([
    "javascript:alert(1)",
    " javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "data:text/html,x",
    "vbscript:x",
    "//example.ac.kr/x",
    "/relative",
    "https://user:pw@example.ac.kr/",
    "https://example.ac.kr/\nx",
    "https://example.ac.kr/" + "a".repeat(2048),
    "",
    null,
  ])("rejects %o", (url) => {
    expect(safeSourceUrl(url)).toBeNull();
  });

  const checked = "2026-10-01T00:00:00Z";
  it("keeps a fully cited official record", () => {
    expect(citationOf({ source_kind: "OFFICIAL_PUBLIC", source_url: "https://example.ac.kr/c", checked_at: checked })).toEqual({
      kind: "OFFICIAL_PUBLIC",
      url: "https://example.ac.kr/c",
      checkedAt: checked,
    });
  });

  it.each([
    { source_url: "javascript:alert(1)", checked_at: checked },
    { source_url: "https://example.ac.kr/c", checked_at: null },
    { source_url: "https://example.ac.kr/c", checked_at: "not-a-date" },
    { source_url: null, checked_at: checked },
  ])("downgrades an uncited official record to UNKNOWN: %o", (fields) => {
    expect(citationOf({ source_kind: "OFFICIAL_PUBLIC", ...fields })).toEqual({ kind: "UNKNOWN", url: null, checkedAt: null });
  });

  it.each(["DEMO", "UNKNOWN"] as const)("never links a %s record", (kind) => {
    expect(citationOf({ source_kind: kind, source_url: "https://example.ac.kr/c", checked_at: checked })).toEqual({
      kind,
      url: null,
      checkedAt: null,
    });
  });
});
