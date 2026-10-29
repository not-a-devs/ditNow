// Real shared client (requestData) with a stubbed fetch: final URLs, bodies, headers, guards.
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../lib/api";
import { channelsApi, isFreeChannel, validateDescription, validateName, validateReason } from "./api";
import { CID, DEPT, channel, request } from "./fixtures.test-data";

function stub(data: unknown, status = 200) {
  const fetch = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
    new Response(JSON.stringify(status < 400 ? { data } : { code: data }), { status }),
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const lastUrl = (fetch: ReturnType<typeof stub>) => new URL(String(fetch.mock.calls.at(-1)![0]));
const lastInit = (fetch: ReturnType<typeof stub>) => fetch.mock.calls.at(-1)![1]!;

afterEach(() => vi.unstubAllGlobals());

describe("channels api paths", () => {
  it("prefixes /api/v1 exactly once and bounds pagination", async () => {
    const fetch = stub({ items: [channel()], next_before: 3 });
    await channelsApi.listDepartment(DEPT, 7);
    const url = lastUrl(fetch);
    expect(url.pathname).toBe(`/api/v1/departments/${DEPT}/free-channels`);
    expect(url.searchParams.get("limit")).toBe("20");
    expect(url.searchParams.get("before")).toBe("7");
    await channelsApi.listMine();
    expect(lastUrl(fetch).pathname).toBe("/api/v1/me/free-channels");
  });

  it("sends create with idempotency key and no client-chosen owner/official fields", async () => {
    const fetch = stub({ channel: channel(), replayed: false });
    await channelsApi.create({ department_id: DEPT, grade: null, name: "스터디", description: "" }, "web-key-000000000001");
    const init = lastInit(fetch);
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["Idempotency-Key"]).toBe("web-key-000000000001");
    expect(Object.keys(JSON.parse(String(init.body))).sort()).toEqual(["department_id", "description", "grade", "name"]);
    expect(lastUrl(fetch).pathname).toBe("/api/v1/free-channels");
  });

  it("sends CAS revision for update/archive and key for official request", async () => {
    let fetch = stub(channel({ revision: 2 }));
    await channelsApi.update(CID, "새", "", 1);
    expect(JSON.parse(String(lastInit(fetch).body))).toEqual({ name: "새", description: "", expected_revision: 1 });
    expect(lastInit(fetch).method).toBe("PATCH");
    await channelsApi.archive(CID, 2);
    expect(lastUrl(fetch).pathname).toBe(`/api/v1/free-channels/${CID}/archive`);
    fetch = stub({ request: request(), replayed: false });
    await channelsApi.requestOfficial(CID, "사유입니다 열글자 이상", "web-key-000000000002");
    expect(lastUrl(fetch).pathname).toBe(`/api/v1/free-channels/${CID}/official-requests`);
  });

  it("refuses non-UUID path ids before any request", async () => {
    const fetch = stub({});
    for (const bad of ["../admin", "채널", "%2e%2e", `${CID}/../x`]) {
      await expect(channelsApi.join(bad)).rejects.toBeInstanceOf(ApiError);
    }
    expect(fetch).not.toHaveBeenCalled();
  });

  it("rejects responses that claim official status or unknown review state", async () => {
    stub({ items: [channel({ is_official: true })], next_before: null });
    await expect(channelsApi.listMine()).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
    stub({ items: [request({ status: "APPROVED" })], next_before: null });
    await expect(channelsApi.myRequests()).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
    stub({ items: [request({ review_state: "IN_REVIEW" })], next_before: null });
    await expect(channelsApi.myRequests()).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
    expect(isFreeChannel(channel({ kind: "DEPARTMENT_ALL" }))).toBe(false);
    expect(isFreeChannel(channel({ id: "not-uuid" }))).toBe(false);
  });

  it("surfaces 503 as UNAVAILABLE", async () => {
    stub("UNAVAILABLE", 503);
    await expect(channelsApi.listMine()).rejects.toMatchObject({ code: "UNAVAILABLE", status: 503 });
  });

  it("accepts only a minimal own leave receipt and rejects metadata or another ID", async () => {
    const controller = new AbortController();
    let fetch = stub({ channel_id: CID, changed: true, membership: "ABSENT" });
    expect(await channelsApi.leave(CID, controller.signal)).toEqual({ channel_id: CID, changed: true, membership: "ABSENT" });
    // Shared transport owns its timeout controller and forwards caller cancellation to it.
    expect(lastInit(fetch).signal).toBeInstanceOf(AbortSignal);
    expect(lastUrl(fetch).pathname).toBe(`/api/v1/free-channels/${CID}/leave`);
    stub({ channel_id: CID, changed: true, membership: "ABSENT", channel: channel() });
    await expect(channelsApi.leave(CID)).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
    fetch = stub({ channel_id: DEPT, changed: true, membership: "ABSENT" });
    await expect(channelsApi.leave(CID)).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });
});

describe("channels validation mirrors server", () => {
  it("counts NFC code points and rejects invisible/control characters", () => {
    expect(validateName("가".repeat(39) + "가")).toBeNull();
    expect(validateName("가".repeat(41))).not.toBeNull();
    expect(validateName("   ")).not.toBeNull();
    expect(validateName("bad‮name")).not.toBeNull();
    expect(validateName("zero​width")).not.toBeNull();
    expect(validateName("line\nbreak")).not.toBeNull();
    expect(validateName("팀\u{1f468}‍\u{1f469}")).toBeNull();
    expect(validateDescription("여러 줄\n설명")).toBeNull();
    expect(validateDescription("x‮")).not.toBeNull();
    expect(validateReason("짧음")).not.toBeNull();
    expect(validateReason("충분히 긴 신청 사유입니다")).toBeNull();
  });
});
