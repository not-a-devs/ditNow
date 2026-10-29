// Test-only server-shaped records (fictional IDs). Not imported by runtime code.
export const DEPT = "00000000-0000-4000-8000-0000000000d1";
export const CID = "00000000-0000-4000-8000-0000000000c1";
export const RID = "00000000-0000-4000-8000-0000000000e1";

export const channel = (over: Record<string, unknown> = {}) => ({
  id: CID,
  department_id: DEPT,
  grade: null,
  kind: "FREE",
  is_official: false,
  name: "알고리즘 스터디",
  description: "",
  status: "ACTIVE",
  revision: 1,
  member_count: 1,
  my_role: "OWNER",
  created_at: "2026-10-30T00:00:00Z",
  archived_at: null,
  ...over,
});

export const request = (over: Record<string, unknown> = {}) => ({
  id: RID,
  channel_id: CID,
  status: "PENDING",
  review_state: "BLOCKED_APPROVER_POLICY",
  reason: "학과 공식 학습 공동체로 운영",
  revision: 1,
  created_at: "2026-10-30T00:00:00Z",
  updated_at: "2026-10-30T00:00:00Z",
  ...over,
});
