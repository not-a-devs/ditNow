// Hand-written mirror of the dormant channels router (not in the OpenAPI snapshot yet).
// Replace with generated types once root mounts the router and regenerates api.d.ts.

export type ChannelStatus = "ACTIVE" | "ARCHIVED";
export type MemberRole = "OWNER" | "MEMBER";
export type RequestStatus = "PENDING" | "CANCELLED";

export interface FreeChannel {
  id: string;
  department_id: string;
  grade: number | null;
  kind: "FREE";
  is_official: false;
  name: string;
  description: string;
  status: ChannelStatus;
  revision: number;
  member_count: number;
  my_role: MemberRole | null;
  created_at: string;
  archived_at: string | null;
}

export interface ChannelPage {
  items: FreeChannel[];
  next_before: number | null;
}

export interface MembershipResult {
  channel: FreeChannel;
  changed: boolean;
}

export interface CreatedChannel {
  channel: FreeChannel;
  replayed: boolean;
}

export interface OfficialRequest {
  id: string;
  channel_id: string;
  status: RequestStatus;
  review_state: "BLOCKED_APPROVER_POLICY";
  reason: string;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface CreatedRequest {
  request: OfficialRequest;
  replayed: boolean;
}

export interface RequestPage {
  items: OfficialRequest[];
  next_before: number | null;
}

export interface ChannelInput {
  department_id: string;
  grade: number | null;
  name: string;
  description: string;
}
