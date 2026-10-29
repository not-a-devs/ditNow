// Mirrors services/api/app/features/collaboration/schemas.py. The router is not mounted yet, so
// these are hand-written (not generated) and every response is checked by ./guards at runtime.

export interface Page<T> {
  items: T[];
  limit: number;
  offset: number;
  has_more: boolean;
}

// Anonymous zone: no author, user, alias or profile field exists on these types.
export interface PostSummary {
  id: string;
  display_name: string;
  title: string;
  excerpt: string;
  comment_count: number;
  /** The caller's own bookmark state for this post. */
  bookmarked: boolean;
  created_at: string;
}

export interface Comment {
  id: string;
  post_id: string;
  display_name: string;
  body: string;
  is_mine: boolean;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface Bookmark {
  post: PostSummary;
  bookmarked_at: string;
}

export interface BookmarkState {
  post_id: string;
  bookmarked: boolean;
}

export const REPORT_REASONS = [
  ["spam", "스팸·광고"],
  ["abuse", "욕설·비방"],
  ["hate", "혐오 표현"],
  ["sexual", "음란물"],
  ["privacy", "개인정보 노출"],
  ["misinformation", "허위 정보"],
  ["other", "기타"],
] as const;

export type ReportReason = (typeof REPORT_REASONS)[number][0];
export type ReportTargetType = "anonymous_post" | "anonymous_comment";

export interface Report {
  id: string;
  target_type: ReportTargetType;
  target_id: string;
  reason: ReportReason;
  status: "submitted";
  created_at: string;
}

// Real-name zone.
export type GroupKind = "study" | "club";
export type JoinMode = "open" | "approval";
export type MembershipStatus = "pending" | "active" | "rejected" | "left";
export type SourceKind = "OFFICIAL_PUBLIC" | "DEMO" | "USER_DEMO" | "UNKNOWN";

export interface MyMembership {
  id: string;
  role: "leader" | "member";
  status: MembershipStatus;
  revision: number;
}

export interface Group {
  id: string;
  kind: GroupKind;
  name: string;
  description: string;
  join_mode: JoinMode;
  capacity: number;
  member_count: number;
  status: "open" | "closed";
  origin: "member_created" | "catalog";
  source: { kind: SourceKind; url: string | null; checked_at: string | null };
  policy_basis: "DEMO_DESIGN_DEFAULT";
  leader: { display_name: string | null };
  my_membership: MyMembership | null;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface GroupInput {
  kind: GroupKind;
  name: string;
  description: string;
  join_mode: JoinMode;
  capacity: number;
}

export interface JoinRequest {
  id: string;
  group_id: string;
  applicant: { display_name: string | null };
  status: MembershipStatus;
  revision: number;
  created_at: string;
}

export interface SpacePost {
  id: string;
  group_id: string;
  author: { display_name: string | null };
  is_mine: boolean;
  body: string;
  revision: number;
  created_at: string;
}

export interface Deleted {
  id: string;
  deleted: boolean;
}
