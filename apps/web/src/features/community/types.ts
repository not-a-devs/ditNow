// Feature-local mirror of services/api/app/features/community/schemas.py.
// Replace with OpenAPI-generated types once the root owner mounts the community router.
// Anonymous post types intentionally have no author/user/identity fields.

export type PostStatus = "active" | "hidden" | "deleted";
export type RecruitmentStatus = "open" | "closed" | "cancelled";

export interface AnonymousPost {
  id: string;
  display_name: "익명";
  title: string;
  body: string;
  status: PostStatus;
  comment_count: number;
  is_mine: boolean;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface Page<T> {
  items: T[];
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface AnonymousPostInput {
  title: string;
  body: string;
}

export interface Recruitment {
  id: string;
  owner: { display_name: string | null };
  is_mine: boolean;
  title: string;
  body: string;
  field: string;
  roles: string[];
  capacity: number;
  accepted_count: number;
  deadline_at: string;
  status: RecruitmentStatus;
  opportunity_id: string | null;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface RecruitmentInput {
  title: string;
  body: string;
  field: string;
  roles: string[];
  capacity: number;
  deadline_at: string;
}

// PATCH body minus `revision`; at least one field. `opportunity_id` is fixed at creation.
export type RecruitmentUpdate = Partial<RecruitmentInput>;

// capacityMax 20 is a demo design default mirrored from the server, not an approved policy.
export const LIMITS = {
  titleMin: 2,
  titleMax: 120,
  bodyMax: 5000,
  capacityMin: 2,
  capacityMax: 20,
  fieldMax: 30,
  roleMax: 30,
  rolesMax: 10,
} as const;
