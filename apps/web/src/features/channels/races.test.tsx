// Real shared transport with deliberately abort-ignoring deferred fetches. No real auth/DB.
import { StrictMode } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ChannelsPage from "./index";
import { CID, DEPT, channel, request } from "./fixtures.test-data";

const OTHER_DEPT = "00000000-0000-4000-8000-0000000000d2";
const OTHER_CID = "00000000-0000-4000-8000-0000000000c2";
const ok = (data: unknown) => new Response(JSON.stringify({ data }), { status: 200 });
const page = (items: unknown[], next_before: number | null = null) => ({ items, next_before });
const denied = (status: number) => new Response(JSON.stringify({ code: status === 401 ? "UNAUTHORIZED" : "FORBIDDEN" }), { status });
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
function stub(handler: (url: URL, init: RequestInit) => Response | Promise<Response>) {
  const fetch = vi.fn((url: RequestInfo | URL, init: RequestInit = {}) => handler(new URL(String(url)), init));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

type Operation = "create" | "update" | "archive" | "join" | "leave" | "official";
const operations: Operation[] = ["create", "update", "archive", "join", "leave", "official"];
function initial(kind: Operation) {
  return channel({ name: "PRIVATE-OLD", my_role: kind === "join" ? null : kind === "leave" ? "MEMBER" : "OWNER" });
}
async function begin(kind: Operation) {
  const item = await screen.findByRole("listitem", { name: "PRIVATE-OLD" });
  if (kind === "create") {
    const form = screen.getByRole("form", { name: "자유 채널 만들기" });
    fireEvent.change(within(form).getByLabelText("채널 이름"), { target: { value: "LATE-CREATED" } });
    fireEvent.submit(form);
  } else if (kind === "update") {
    fireEvent.click(within(item).getByRole("button", { name: "수정" }));
    fireEvent.change(within(item).getByLabelText("새 채널 이름"), { target: { value: "LATE-UPDATED" } });
    fireEvent.submit(within(item).getByRole("form", { name: "채널 수정" }));
  } else if (kind === "official") {
    fireEvent.change(within(item).getByLabelText("공식 채널 신청 사유"), { target: { value: "가상 공식 채널 신청 사유입니다" } });
    fireEvent.submit(within(item).getByRole("form", { name: "공식 채널 신청" }));
  } else fireEvent.click(within(item).getByRole("button", { name: kind === "archive" ? "보관" : kind === "join" ? "참여" : "나가기" }));
}
function result(kind: Operation) {
  if (kind === "create") return { channel: channel({ name: "LATE-CREATED" }), replayed: false };
  if (kind === "official") return { request: request(), replayed: false };
  if (kind === "leave") return { channel_id: CID, changed: true, membership: "ABSENT" };
  if (kind === "join") return { channel: channel({ name: "LATE-JOINED", my_role: "MEMBER" }), changed: true };
  return channel({ name: "LATE-UPDATED", status: kind === "archive" ? "ARCHIVED" : "ACTIVE" });
}

describe("channels scope and request lifetime", () => {
  it("drops an old department read even when fetch resolves after abort", async () => {
    const late = deferred<Response>();
    let signal: AbortSignal | null | undefined;
    stub((url, init) => {
      if (url.pathname.includes("official-channel-requests")) return ok(page([]));
      if (url.pathname.includes(DEPT)) { signal = init.signal; return late.promise; }
      return ok(page([channel({ id: OTHER_CID, department_id: OTHER_DEPT, name: "CURRENT-NEW" })]));
    });
    const view = render(<ChannelsPage departmentId={DEPT} grade={2} />);
    view.rerender(<ChannelsPage departmentId={OTHER_DEPT} grade={3} />);
    await screen.findByRole("listitem", { name: "CURRENT-NEW" });
    expect(signal?.aborted).toBe(true);
    await act(async () => late.resolve(ok(page([channel({ name: "PRIVATE-OLD" })]))));
    expect(screen.queryByText("PRIVATE-OLD")).not.toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "CURRENT-NEW" })).toBeInTheDocument();
  });

  it.each(["grade", "session"])("clears and reloads on a %s-only change", async field => {
    let calls = 0;
    const late = deferred<Response>();
    stub(url => {
      if (url.pathname.includes("official-channel-requests")) return ok(page([]));
      return ++calls === 1 ? ok(page([channel({ name: "PRIVATE-OLD" })])) : late.promise;
    });
    const view = render(<ChannelsPage departmentId={DEPT} grade={2} sessionGeneration={1} />);
    await screen.findByText("PRIVATE-OLD");
    view.rerender(<ChannelsPage departmentId={DEPT} grade={field === "grade" ? 3 : 2} sessionGeneration={field === "session" ? 2 : 1} />);
    expect(screen.queryByText("PRIVATE-OLD")).not.toBeInTheDocument();
    expect(calls).toBe(2);
    await act(async () => late.resolve(ok(page([channel({ name: "CURRENT-NEW" })]))));
    expect(await screen.findByText("CURRENT-NEW")).toBeInTheDocument();
  });

  it("does not append a late old-scope pagination result", async () => {
    const late = deferred<Response>();
    let signal: AbortSignal | null | undefined;
    stub((url, init) => {
      if (url.pathname.includes("official-channel-requests")) return ok(page([]));
      if (url.searchParams.has("before")) { signal = init.signal; return late.promise; }
      return ok(url.pathname.includes(OTHER_DEPT) ? page([channel({ id: OTHER_CID, name: "CURRENT-NEW" })]) : page([channel()], 4));
    });
    const view = render(<ChannelsPage departmentId={DEPT} />);
    fireEvent.click(await screen.findByRole("button", { name: "더 보기" }));
    view.rerender(<ChannelsPage departmentId={OTHER_DEPT} />);
    await screen.findByText("CURRENT-NEW");
    expect(signal?.aborted).toBe(true);
    await act(async () => late.resolve(ok(page([channel({ name: "LATE-PAGE" })]))));
    expect(screen.queryByText("LATE-PAGE")).not.toBeInTheDocument();
  });

  it.each(operations)("ignores an aborted %s response after a department change", async kind => {
    const late = deferred<Response>();
    let signal: AbortSignal | null | undefined;
    stub((url, init) => {
      if (init.method) { signal = init.signal; return late.promise; }
      if (url.pathname.includes("official-channel-requests")) return ok(page([]));
      return ok(page([url.pathname.includes(OTHER_DEPT) ? channel({ id: OTHER_CID, name: "CURRENT-NEW" }) : initial(kind)]));
    });
    const view = render(<ChannelsPage departmentId={DEPT} grade={2} />);
    await begin(kind);
    view.rerender(<ChannelsPage departmentId={OTHER_DEPT} grade={3} />);
    await screen.findByText("CURRENT-NEW");
    expect(signal?.aborted).toBe(true);
    await act(async () => late.resolve(ok(result(kind))));
    expect(screen.queryByText(/LATE-/)).not.toBeInTheDocument();
    expect(screen.queryByText("PRIVATE-OLD")).not.toBeInTheDocument();
    expect(screen.queryByText(/접수됨 · 승인 절차 보류/)).not.toBeInTheDocument();
    expect(screen.getByText("CURRENT-NEW")).toBeInTheDocument();
  });

  it.each(operations)("removes all private state on a current %s 403", async kind => {
    const fetch = stub((url, init) => {
      if (init.method) return denied(403);
      if (url.pathname.includes("official-channel-requests")) return ok(page([request()]));
      return ok(page([initial(kind)]));
    });
    render(<ChannelsPage departmentId={DEPT} />);
    await begin(kind);
    expect(await screen.findByRole("alert")).toHaveTextContent("현재 소속");
    expect(screen.queryByText("PRIVATE-OLD")).not.toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "자유 채널 만들기" })).not.toBeInTheDocument();
    expect(screen.queryByText(/접수됨 · 승인 절차 보류/)).not.toBeInTheDocument();
    expect(fetch.mock.calls.some(([, init]) => init?.method)).toBe(true);
  });

  it("ignores an old write's late 403 instead of clearing a newer session", async () => {
    const late = deferred<Response>();
    stub((url, init) => {
      if (init.method) return late.promise;
      if (url.pathname.includes("official-channel-requests")) return ok(page([]));
      return ok(page([channel({ name: url.pathname.includes(OTHER_DEPT) ? "CURRENT-NEW" : "PRIVATE-OLD" })]));
    });
    const view = render(<ChannelsPage departmentId={DEPT} sessionGeneration={1} />);
    await begin("create");
    view.rerender(<ChannelsPage departmentId={OTHER_DEPT} sessionGeneration={2} />);
    await screen.findByText("CURRENT-NEW");
    await act(async () => late.resolve(denied(403)));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("CURRENT-NEW")).toBeInTheDocument();
  });

  it("reloads after a minimal leave receipt instead of inventing channel state", async () => {
    let joined = true, reads = 0;
    stub((url, init) => {
      if (init.method) { joined = false; return ok({ channel_id: CID, changed: true, membership: "ABSENT" }); }
      if (url.pathname.includes("official-channel-requests")) return ok(page([]));
      reads++;
      return ok(page([channel({ name: "PRIVATE-OLD", my_role: joined ? "MEMBER" : null, member_count: joined ? 2 : 1 })]));
    });
    render(<ChannelsPage departmentId={DEPT} />);
    await begin("leave");
    expect(await screen.findByRole("button", { name: "참여" })).toBeInTheDocument();
    expect(screen.getByText("1명")).toBeInTheDocument();
    expect(reads).toBe(2);
  });

  it("clears on pagination 401 and can start a new session scope", async () => {
    let expired = true;
    stub(url => {
      if (url.pathname.includes("official-channel-requests")) return ok(page([]));
      if (url.searchParams.has("before") && expired) return denied(401);
      return ok(page([channel({ name: "PRIVATE-OLD" })], 4));
    });
    const view = render(<ChannelsPage departmentId={DEPT} sessionGeneration={1} />);
    fireEvent.click(await screen.findByRole("button", { name: "더 보기" }));
    await screen.findByRole("alert");
    expect(screen.queryByText("PRIVATE-OLD")).not.toBeInTheDocument();
    expired = false;
    view.rerender(<ChannelsPage departmentId={DEPT} sessionGeneration={2} />);
    expect(await screen.findByText("PRIVATE-OLD")).toBeInTheDocument();
  });

  it("guards StrictMode's first read and same-tick duplicate writes", async () => {
    const first = deferred<Response>(), write = deferred<Response>();
    let reads = 0, writes = 0;
    const fetch = stub((url, init) => {
      if (init.method) { writes++; return write.promise; }
      if (url.pathname.includes("official-channel-requests")) return ok(page([]));
      return ++reads === 1 ? first.promise : ok(page([]));
    });
    render(<StrictMode><ChannelsPage departmentId={DEPT} /></StrictMode>);
    const form = await screen.findByRole("form", { name: "자유 채널 만들기" });
    await act(async () => first.resolve(ok(page([channel({ name: "STRICT-STALE" })]))));
    expect(screen.queryByText("STRICT-STALE")).not.toBeInTheDocument();
    fireEvent.change(within(form).getByLabelText("채널 이름"), { target: { value: "LATE-CREATED" } });
    fireEvent.submit(form); fireEvent.submit(form);
    expect(writes).toBe(1);
    expect(within(form).getByLabelText("채널 이름")).toBeDisabled();
    const post = fetch.mock.calls.find(([, init]) => init?.method);
    expect(post?.[1]?.signal).toBeInstanceOf(AbortSignal);
    await act(async () => write.resolve(ok(result("create"))));
    expect(await screen.findByText("LATE-CREATED")).toBeInTheDocument();
  });
});
