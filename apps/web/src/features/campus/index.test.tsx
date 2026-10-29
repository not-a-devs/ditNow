// UI states over the real shared client with a stubbed fetch (no server, no DB).
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CampusPage from "./index";

type Handler = (url: URL, init: RequestInit) => Response | Promise<Response>;

const ok = (data: unknown) => new Response(JSON.stringify({ data }), { status: 200 });
const fail = (status: number, code: string) =>
  new Response(JSON.stringify({ code, message: "server-secret-detail", request_id: "12345678-1234-1234-1234-123456789012" }), { status });

function stubApi(handler: Handler) {
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => handler(new URL(String(input)), init));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const CHANNELS = { items: [{ id: "ch-all", department_id: "dept-a", kind: "DEPARTMENT_ALL", name: "가상학과", grade: null }] };

function message(id: string, body: string, isMine = false) {
  return { id, channel_id: "ch-all", seq: 1, kind: "TEXT", body, author_id: null, is_mine: isMine, notice: null, created_at: "2026-10-30T00:00:00Z" };
}

function posts(fetch: ReturnType<typeof stubApi>) {
  return fetch.mock.calls
    .filter(([, init]) => init?.method === "POST")
    .map(([, init]) => JSON.parse(String(init?.body)) as { body: string; client_nonce: string });
}

describe("campus page states", () => {
  it("does not request chat without a session department", () => {
    const fetch = stubApi(() => ok({ items: [] }));
    render(<CampusPage />);
    expect(screen.getByText(/소속 학과 정보가 아직 연결되지 않았습니다/)).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("shows loading, then 503 as not-ready with retry that recovers", async () => {
    let release!: () => void;
    let calls = 0;
    stubApi(async () => {
      calls += 1;
      if (calls === 1) {
        await new Promise<void>((resolve) => (release = resolve));
        return fail(503, "UNAVAILABLE");
      }
      return ok(CHANNELS);
    });
    render(<CampusPage departmentId="dept-a" />);
    expect(screen.getByRole("status")).toHaveTextContent("채널 불러오는 중");
    release();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("서버 연결 준비 중");
    expect(alert).not.toHaveTextContent("server-secret-detail");
    expect(alert).toHaveTextContent("12345678-1234-1234-1234-123456789012");
    fireEvent.click(within(alert).getByRole("button", { name: "다시 시도" }));
    expect(await screen.findByRole("button", { name: /학과 전체 · 가상학과/ })).toBeInTheDocument();
  });

  it("shows 401 as login required without a retry loop", async () => {
    stubApi(() => fail(401, "UNAUTHORIZED"));
    render(<CampusPage departmentId="dept-a" />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("로그인이 필요합니다");
    expect(within(alert).queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows 403 as out of scope", async () => {
    stubApi(() => fail(403, "FORBIDDEN"));
    render(<CampusPage departmentId="dept-b" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("현재 소속 학과·학년 범위가 아닙니다.");
  });

  it("shows network failures with retry and no leaked detail", async () => {
    stubApi(() => Promise.reject(new Error("secret-network-detail")));
    render(<CampusPage departmentId="dept-a" />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("네트워크 오류");
    expect(alert).not.toHaveTextContent("secret-network-detail");
    expect(within(alert).getByRole("button", { name: "다시 시도" })).toBeEnabled();
  });
});

describe("chat sending", () => {
  function chatServer(onPost: (body: { body: string; client_nonce: string }) => Response) {
    return stubApi((url, init) => {
      if (url.pathname === "/api/v1/departments/dept-a/channels") return ok(CHANNELS);
      if (url.pathname === "/api/v1/channels/ch-all/messages" && init.method === "POST") {
        return onPost(JSON.parse(String(init.body)));
      }
      if (url.pathname === "/api/v1/channels/ch-all/messages") return ok({ items: [], next_before: null });
      return fail(404, "NOT_FOUND");
    });
  }

  async function ready() {
    render(<CampusPage departmentId="dept-a" />);
    await screen.findByText("아직 메시지가 없습니다.");
    return screen.getByLabelText("메시지 입력");
  }

  it("rejects empty input locally without calling the server", async () => {
    const fetch = chatServer(() => ok({}));
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("메시지를 입력하세요.");
    expect(posts(fetch)).toEqual([]);
  });

  it("retries an uncertain failure with the same body and the same key", async () => {
    let attempt = 0;
    const fetch = chatServer((body) => {
      attempt += 1;
      return attempt === 1 ? fail(503, "UNAVAILABLE") : ok({ message: message("m1", body.body, true), replayed: true });
    });
    const input = await ready();
    fireEvent.change(input, { target: { value: "  안녕하세요  " } });
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));
    expect(await screen.findByRole("note")).toHaveTextContent("같은 내용으로 다시 보내면 중복 없이 처리됩니다.");
    expect(input).toHaveValue("  안녕하세요  ");
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));
    expect(await screen.findByText("안녕하세요")).toBeInTheDocument();
    const [first, second] = posts(fetch);
    expect(second).toEqual(first);
    expect(first.body).toBe("안녕하세요");
    expect(input).toHaveValue("");
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });

  it("uses a new key once the body is edited after a failure, and warns it may duplicate", async () => {
    const fetch = chatServer(() => Promise.reject(new Error("offline")) as never);
    const input = await ready();
    fireEvent.change(input, { target: { value: "첫 내용" } });
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));
    await screen.findByRole("note");
    fireEvent.change(input, { target: { value: "고친 내용" } });
    expect(screen.getByRole("note")).toHaveTextContent("이전 메시지가 이미 전송되었을 수 있습니다.");
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));
    await waitFor(() => expect(posts(fetch)).toHaveLength(2));
    const [first, second] = posts(fetch);
    expect(second.body).toBe("고친 내용");
    expect(second.client_nonce).not.toBe(first.client_nonce);
    // Going back to the first body after that is yet another intent.
    fireEvent.change(input, { target: { value: "첫 내용" } });
    await waitFor(() => expect(screen.getByRole("button", { name: "보내기" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));
    await waitFor(() => expect(posts(fetch)).toHaveLength(3));
    expect(new Set(posts(fetch).map((p) => p.client_nonce)).size).toBe(3);
  });

  it("issues a new key after a 409 even for the same body", async () => {
    let attempt = 0;
    const fetch = chatServer((body) => {
      attempt += 1;
      return attempt === 1 ? fail(409, "CONFLICT") : ok({ message: message("m2", body.body, true), replayed: false });
    });
    const input = await ready();
    fireEvent.change(input, { target: { value: "같은 글" } });
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("상태가 변경되었습니다");
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));
    expect(await screen.findByText("같은 글")).toBeInTheDocument();
    const [first, second] = posts(fetch);
    expect(second.body).toBe(first.body);
    expect(second.client_nonce).not.toBe(first.client_nonce);
  });

  it("starts a fresh key for the next message after success", async () => {
    const fetch = chatServer((body) => ok({ message: message(body.client_nonce, body.body, true), replayed: false }));
    const input = await ready();
    for (const text of ["하나", "하나"]) {
      fireEvent.change(input, { target: { value: text } });
      fireEvent.click(screen.getByRole("button", { name: "보내기" }));
      await waitFor(() => expect(input).toHaveValue(""));
    }
    const [first, second] = posts(fetch);
    expect(first.client_nonce).not.toBe(second.client_nonce);
  });
});

describe("official notice cards read the single original", () => {
  it("opens the latest original from a card and refetches on every open", async () => {
    const card = {
      ...message("card-1", "", false),
      kind: "NOTICE_CARD",
      body: null,
      notice: { notice_id: "n-1", title: "카드 v1", status: "PUBLISHED", revision: 1 },
    };
    let revision = 2;
    const original = () => ({
      id: "n-1",
      audience: { type: "DEPARTMENT", department_id: "dept-a", grade: null },
      title: `원본 v${revision}`,
      body: "본문",
      status: "PUBLISHED",
      revision,
      can_manage: false,
      created_at: "2026-10-30T00:00:00Z",
      updated_at: "2026-10-30T00:00:00Z",
      published_at: "2026-10-30T00:00:00Z",
    });
    const fetch = stubApi((url) => {
      if (url.pathname.endsWith("/channels")) return ok(CHANNELS);
      if (url.pathname.endsWith("/messages")) return ok({ items: [card], next_before: null });
      if (url.pathname === "/api/v1/notices/n-1") return ok(original());
      if (url.pathname === "/api/v1/notices") return ok({ items: [original()] });
      return fail(404, "NOT_FOUND");
    });
    render(<CampusPage departmentId="dept-a" />);
    fireEvent.click(await screen.findByRole("button", { name: /카드 v1/ }));
    expect(await screen.findByRole("heading", { name: "원본 v2" })).toBeInTheDocument();
    expect(screen.getByText(/개정 2/)).toBeInTheDocument();
    // The original is revised while the list on screen still shows v2.
    revision = 3;
    fireEvent.click(screen.getByRole("button", { name: "← 공지 목록" }));
    fireEvent.click(await screen.findByRole("button", { name: /원본 v2/ }));
    expect(await screen.findByRole("heading", { name: "원본 v3" })).toBeInTheDocument();
    const detailCalls = fetch.mock.calls.filter(([input]) => new URL(String(input)).pathname === "/api/v1/notices/n-1");
    expect(detailCalls).toHaveLength(2);
  });

  it("shows an unreadable card as hidden instead of guessing its content", async () => {
    const hidden = { ...message("card-2", "", false), kind: "NOTICE_CARD", body: null, notice: null };
    stubApi((url) => (url.pathname.endsWith("/channels") ? ok(CHANNELS) : ok({ items: [hidden], next_before: null })));
    render(<CampusPage departmentId="dept-a" />);
    expect(await screen.findByText("볼 수 없는 공지입니다.")).toBeInTheDocument();
  });
});

describe("academic calendar provenance", () => {
  it("links only cited official records and marks the rest", async () => {
    const term = { id: "t-1", name: "가상 2026-2학기", starts_on: "2026-09-01", ends_on: "2027-02-28", source_kind: "DEMO", source_url: null, checked_at: null };
    const event = (id: string, title: string, kind: string, url: string | null, checked: string | null) => ({
      id, title, starts_on: "2026-09-01", ends_on: "2026-09-01", source_kind: kind, source_url: url, checked_at: checked,
    });
    stubApi((url) => {
      if (url.pathname === "/api/v1/academic/terms") return ok({ items: [term] });
      return ok({
        term,
        items: [
          event("e1", "위조 링크", "OFFICIAL_PUBLIC", "javascript:alert(1)", "2026-10-01T00:00:00Z"),
          event("e2", "확인일 없음", "OFFICIAL_PUBLIC", "https://www.example.ac.kr/c", null),
          event("e3", "정상 인용", "OFFICIAL_PUBLIC", "https://www.example.ac.kr/c", "2026-10-01T00:00:00Z"),
          event("e4", "가상 일정", "DEMO", "https://www.example.ac.kr/c", "2026-10-01T00:00:00Z"),
        ],
      });
    });
    render(<CampusPage />);
    fireEvent.click(screen.getByRole("tab", { name: "학사 일정" }));
    const rows = await screen.findAllByRole("listitem");
    const row = (title: string) => rows.find((li) => li.textContent?.includes(title))!;
    expect(row("위조 링크")).toHaveTextContent("출처 미확인");
    expect(row("확인일 없음")).toHaveTextContent("출처 미확인");
    expect(row("가상 일정")).toHaveTextContent("가상 시연 데이터");
    for (const title of ["위조 링크", "확인일 없음", "가상 일정"]) {
      expect(within(row(title)).queryByRole("link")).not.toBeInTheDocument();
    }
    expect(row("정상 인용")).toHaveTextContent("공개 자료 스냅샷");
    expect(within(row("정상 인용")).getByRole("link", { name: "출처" })).toHaveAttribute("href", "https://www.example.ac.kr/c");
    expect(document.querySelectorAll('a[href^="javascript:"]')).toHaveLength(0);
  });
});
