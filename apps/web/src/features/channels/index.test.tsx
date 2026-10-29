// UI states over the real shared client with a stubbed fetch (no server, no DB, no shell mount).
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ChannelsPage from "./index";
import { CID, DEPT, channel, request } from "./fixtures.test-data";

type Handler = (url: URL, init: RequestInit) => Response | Promise<Response>;

const ok = (data: unknown, status = 200) => new Response(JSON.stringify({ data }), { status });
const fail = (status: number, code: string) =>
  new Response(JSON.stringify({ code, message: "server-secret-detail", request_id: "12345678-1234-1234-1234-123456789012" }), { status });

function stubApi(handler: Handler) {
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => handler(new URL(String(input)), init));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const page = (...items: unknown[]) => ({ items, next_before: null });
const NO_REQUESTS = page();

function listing(items: unknown[], extra?: Handler): Handler {
  return (url, init) => {
    if (url.pathname.endsWith("/me/official-channel-requests")) return ok(NO_REQUESTS);
    if (url.pathname.endsWith("/free-channels") && !init.method) return ok(page(...items));
    return extra ? extra(url, init) : fail(500, "INTERNAL");
  };
}

const keyOf = (init: RequestInit | undefined) => (init?.headers as Record<string, string> | undefined)?.["Idempotency-Key"];

afterEach(() => vi.unstubAllGlobals());

describe("free channels page", () => {
  it("does not call the API without a session department", () => {
    const fetch = stubApi(() => ok(page()));
    render(<ChannelsPage />);
    expect(screen.getByText(/소속 학과 정보가 아직 연결되지 않았습니다/)).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("shows dormant 503 as not-ready without leaking server text, and retry recovers", async () => {
    let calls = 0;
    stubApi((url, init) => {
      calls += 1;
      if (calls <= 2) return fail(503, "UNAVAILABLE");
      return listing([channel()])(url, init);
    });
    render(<ChannelsPage departmentId={DEPT} />);
    expect(screen.getByRole("status")).toHaveTextContent("자유 채널 불러오는 중");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("서버 연결 준비 중");
    expect(alert).toHaveTextContent("자유 채널 API");
    expect(alert).not.toHaveTextContent("server-secret-detail");
    fireEvent.click(within(alert).getByRole("button", { name: "다시 시도" }));
    expect(await screen.findByRole("listitem", { name: "알고리즘 스터디" })).toBeInTheDocument();
  });

  it("shows 403 for another department without retry", async () => {
    stubApi(() => fail(403, "FORBIDDEN"));
    render(<ChannelsPage departmentId={DEPT} />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("현재 소속 학과·학년 범위가 아닙니다");
    expect(within(alert).queryByRole("button")).toBeNull();
  });

  it("offers controls only per server-returned role and never shows an official badge", async () => {
    const other = "00000000-0000-4000-8000-0000000000c2";
    const third = "00000000-0000-4000-8000-0000000000c3";
    stubApi(
      listing(
        [
          channel(),
          channel({ id: other, name: "멤버 채널", my_role: "MEMBER", member_count: 3 }),
          channel({ id: third, name: "미참여 채널", my_role: null, grade: 2 }),
        ],
        (url) => {
          if (url.pathname.endsWith(`${third}/join`)) {
            return ok({ channel: channel({ id: third, name: "미참여 채널", my_role: "MEMBER", grade: 2, member_count: 2 }), changed: true });
          }
          return fail(500, "INTERNAL");
        },
      ),
    );
    render(<ChannelsPage departmentId={DEPT} grade={2} />);
    const owned = await screen.findByRole("listitem", { name: "알고리즘 스터디" });
    expect(within(owned).getByRole("button", { name: "수정" })).toBeInTheDocument();
    expect(within(owned).getByRole("button", { name: "공식 채널 신청" })).toBeInTheDocument();
    const member = screen.getByRole("listitem", { name: "멤버 채널" });
    expect(within(member).getByRole("button", { name: "나가기" })).toBeInTheDocument();
    expect(within(member).queryByRole("button", { name: "수정" })).toBeNull();
    const outside = screen.getByRole("listitem", { name: "미참여 채널" });
    expect(within(outside).getByText(/2학년/)).toBeInTheDocument();
    fireEvent.click(within(outside).getByRole("button", { name: "참여" }));
    expect(await within(outside).findByRole("button", { name: "나가기" })).toBeInTheDocument();
    expect(within(outside).getByText("2명")).toBeInTheDocument();
    // Only the explanatory note may mention badges; no item is labeled official.
    for (const item of screen.getAllByRole("listitem")) {
      expect(within(item).queryByText(/^공식( 채널)?$/)).toBeNull();
      expect(within(item).getByText(/^자유 채널 · /)).toBeInTheDocument();
    }
  });

  it("reuses the idempotency key only for the same payload after an unclear failure", async () => {
    let posts = 0;
    const fetch = stubApi(
      listing([], (url, init) => {
        if (url.pathname.endsWith("/free-channels") && init.method === "POST") {
          posts += 1;
          if (posts === 1) return fail(502, "UNAVAILABLE");
          return ok({ channel: channel({ name: posts === 2 ? "스터디" : "스터디2" }), replayed: posts === 2 }, posts === 2 ? 200 : 201);
        }
        return fail(500, "INTERNAL");
      }),
    );
    render(<ChannelsPage departmentId={DEPT} />);
    const form = await screen.findByRole("form", { name: "자유 채널 만들기" });
    fireEvent.change(within(form).getByLabelText("채널 이름"), { target: { value: "스터디" } });
    fireEvent.click(within(form).getByRole("button", { name: "만들기" }));
    expect(await within(form).findByText(/이미 처리되었을 수 있습니다/)).toBeInTheDocument();
    fireEvent.click(within(form).getByRole("button", { name: "만들기" }));
    expect(await screen.findByRole("listitem", { name: "스터디" })).toBeInTheDocument();
    const keys = fetch.mock.calls.filter(([, init]) => init?.method === "POST").map(([, init]) => keyOf(init));
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
    expect(keys[0]).toMatch(/^[A-Za-z0-9-]{16,100}$/);
  });

  it("validates Unicode names locally before sending", async () => {
    const fetch = stubApi(listing([]));
    render(<ChannelsPage departmentId={DEPT} />);
    const form = await screen.findByRole("form", { name: "자유 채널 만들기" });
    fireEvent.change(within(form).getByLabelText("채널 이름"), { target: { value: "bad‮name" } });
    fireEvent.click(within(form).getByRole("button", { name: "만들기" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("보이지 않는 문자");
    expect(fetch.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });

  it("submits an official request and shows it as pending with approval blocked", async () => {
    const fetch = stubApi(
      listing([channel()], (url, init) => {
        if (url.pathname.endsWith(`${CID}/official-requests`) && init.method === "POST") {
          return ok({ request: request(), replayed: false }, 201);
        }
        return fail(500, "INTERNAL");
      }),
    );
    render(<ChannelsPage departmentId={DEPT} />);
    const owned = await screen.findByRole("listitem", { name: "알고리즘 스터디" });
    fireEvent.change(within(owned).getByLabelText("공식 채널 신청 사유"), { target: { value: "학과 공식 학습 공동체로 운영" } });
    fireEvent.click(within(owned).getByRole("button", { name: "공식 채널 신청" }));
    expect(await screen.findByText(/접수됨 · 승인 절차 보류/)).toBeInTheDocument();
    const sent = fetch.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(sent?.[1]?.body))).toEqual({ reason: "학과 공식 학습 공동체로 운영" });
    expect(within(owned).queryByText(/공식 채널입니다/)).toBeNull();
  });

  it("shows CAS conflict on stale archive and keeps the item", async () => {
    stubApi(
      listing([channel()], (url) => (url.pathname.endsWith("/archive") ? fail(409, "CONFLICT") : fail(500, "INTERNAL"))),
    );
    render(<ChannelsPage departmentId={DEPT} />);
    const owned = await screen.findByRole("listitem", { name: "알고리즘 스터디" });
    fireEvent.click(within(owned).getByRole("button", { name: "보관" }));
    await waitFor(() => expect(within(owned).getByRole("alert")).toHaveTextContent("상태가 변경되었습니다"));
    expect(within(owned).queryByText("보관됨")).toBeNull();
  });
});
