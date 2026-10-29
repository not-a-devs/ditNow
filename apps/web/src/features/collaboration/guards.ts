// Runtime response guards. requestData<T> only casts, so every payload is checked here before it
// reaches React state; a mismatch is treated as an invalid server response, never rendered.
import { ApiError } from "../../lib/api";
import type {
  Bookmark,
  BookmarkState,
  Comment,
  Deleted,
  Group,
  JoinRequest,
  MyMembership,
  Page,
  PostSummary,
  Report,
  SpacePost,
} from "./types";

type Guard<T> = (value: unknown) => value is T;
type Shape = Record<string, (value: unknown) => boolean>;

const str = (v: unknown): v is string => typeof v === "string";
const int = (v: unknown): v is number => Number.isInteger(v);
const bool = (v: unknown): v is boolean => typeof v === "boolean";
const date = (v: unknown): v is string => str(v) && !Number.isNaN(Date.parse(v));
const nullable = (check: (v: unknown) => boolean) => (v: unknown) => v === null || check(v);
const oneOf = (...values: string[]) => (v: unknown) => str(v) && values.includes(v);
const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

function shape<T>(fields: Shape): Guard<T> {
  return (value: unknown): value is T =>
    isRecord(value) && Object.entries(fields).every(([key, check]) => check(value[key]));
}

// Anonymous-zone payloads must have exactly the expected keys: if an author/user/profile field
// ever leaks into a response, the UI refuses it instead of silently ignoring it.
function exact<T>(fields: Shape): Guard<T> {
  const loose = shape<T>(fields);
  const expected = Object.keys(fields).sort().join(",");
  return (value: unknown): value is T => loose(value) && Object.keys(value as object).sort().join(",") === expected;
}

const name = shape<{ display_name: string | null }>({ display_name: nullable(str) });

export const isPostSummary = exact<PostSummary>({
  id: str, display_name: str, title: str, excerpt: str, comment_count: int, created_at: date,
});
export const isComment = exact<Comment>({
  id: str, post_id: str, display_name: str, body: str, is_mine: bool, revision: int,
  created_at: date, updated_at: date,
});
export const isBookmark = exact<Bookmark>({ post: isPostSummary, bookmarked_at: date });
export const isBookmarkState = shape<BookmarkState>({ post_id: str, bookmarked: bool });
export const isReport = exact<Report>({
  id: str,
  target_type: oneOf("anonymous_post", "anonymous_comment"),
  target_id: str,
  reason: oneOf("spam", "abuse", "hate", "sexual", "privacy", "misinformation", "other"),
  status: oneOf("submitted"),
  created_at: date,
});
export const isMembership = shape<MyMembership>({
  id: str, role: oneOf("leader", "member"), status: oneOf("pending", "active", "rejected", "left"), revision: int,
});
export const isGroup = shape<Group>({
  id: str,
  kind: oneOf("study", "club"),
  name: str,
  description: str,
  join_mode: oneOf("open", "approval"),
  capacity: int,
  member_count: int,
  status: oneOf("open", "closed"),
  origin: oneOf("member_created", "catalog"),
  source: shape({
    kind: oneOf("OFFICIAL_PUBLIC", "DEMO", "USER_DEMO", "UNKNOWN"),
    url: nullable(str),
    checked_at: nullable(date),
  }),
  policy_basis: oneOf("DEMO_DESIGN_DEFAULT"),
  leader: name,
  my_membership: nullable(isMembership),
  revision: int,
  created_at: date,
  updated_at: date,
});
export const isJoinRequest = shape<JoinRequest>({
  id: str, group_id: str, applicant: name, status: oneOf("pending", "active", "rejected", "left"),
  revision: int, created_at: date,
});
export const isSpacePost = shape<SpacePost>({
  id: str, group_id: str, author: name, is_mine: bool, body: str, revision: int, created_at: date,
});
export const isDeleted = shape<Deleted>({ id: str, deleted: bool });

export function pageOf<T>(item: Guard<T>): Guard<Page<T>> {
  return (value: unknown): value is Page<T> =>
    isRecord(value) && Array.isArray(value.items) && value.items.every(item)
    && int(value.limit) && int(value.offset) && bool(value.has_more);
}

export function ensure<T>(guard: Guard<T>) {
  return (value: unknown): T => {
    if (!guard(value)) throw new ApiError("INVALID_RESPONSE", 200);
    return value;
  };
}

/** Only an https link without credentials is ever rendered as a link. */
export function safeLink(value: string | null): string | null {
  if (!value || value.length > 2048 || /[\s\u0000-\u001f\u007f-\u009f]/.test(value)) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname && !url.username && !url.password && !url.hash ? url.href : null;
  } catch {
    return null;
  }
}
