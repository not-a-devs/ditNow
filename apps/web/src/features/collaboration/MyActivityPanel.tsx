import { BookmarkButton } from "./AnonymousPanel";
import { collaborationApi } from "./api";
import { REPORT_REASONS } from "./types";
import { RemoteView, formatTime, useRemote } from "./ui";

const REASON_LABEL = Object.fromEntries(REPORT_REASONS) as Record<string, string>;

// Personal views: only the caller's own bookmarks and report receipts.
export function MyActivityPanel() {
  const bookmarks = useRemote(signal => collaborationApi.listBookmarks(signal), "bookmarks");
  const reports = useRemote(signal => collaborationApi.listReports(signal), "reports");
  return (
    <div className="space-y-6">
      <section aria-labelledby="my-bookmarks" className="space-y-2">
        <h2 id="my-bookmarks" className="text-lg font-semibold">내 북마크</h2>
        <RemoteView remote={bookmarks.state} label="북마크" isEmpty={p => p.items.length === 0} onRetry={bookmarks.reload}>
          {page => (
            <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200">
              {page.items.map(item => (
                <li key={item.post.id} className="p-3 text-sm">
                  <p className="font-medium">{item.post.title}</p>
                  <p className="text-slate-600">{item.post.excerpt}</p>
                  <p className="text-xs text-slate-500">저장 {formatTime(item.bookmarked_at)}</p>
                  <BookmarkButton postId={item.post.id} initial={item.post.bookmarked} />
                </li>
              ))}
            </ul>
          )}
        </RemoteView>
      </section>
      <section aria-labelledby="my-reports" className="space-y-2">
        <h2 id="my-reports" className="text-lg font-semibold">내 신고 요청</h2>
        <p className="text-xs text-slate-500">사유만 기록됩니다. 운영자 검토·제재·이의신청은 정책 승인 전이라 제공하지 않습니다.</p>
        <RemoteView remote={reports.state} label="신고 요청" isEmpty={p => p.items.length === 0} onRetry={reports.reload}>
          {page => (
            <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200">
              {page.items.map(item => (
                <li key={item.id} className="p-3 text-sm">
                  {item.target_type === "anonymous_post" ? "익명 글" : "익명 댓글"} · {REASON_LABEL[item.reason]} · 접수 요청됨 · {formatTime(item.created_at)}
                </li>
              ))}
            </ul>
          )}
        </RemoteView>
      </section>
    </div>
  );
}
