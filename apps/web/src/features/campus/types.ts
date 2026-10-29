// Hand-written mirror of services/api/app/features/campus/schemas.py.
// Replace with OpenAPI-generated types once root mounts the campus router.

export type AudienceType = "SCHOOL" | "DEPARTMENT" | "DEPARTMENT_GRADE";

export interface Audience {
  type: AudienceType;
  department_id?: string | null;
  grade?: number | null;
}

export type ChannelKind = "DEPARTMENT_ALL" | "DEPARTMENT_GRADE";

export interface Channel {
  id: string;
  department_id: string;
  kind: ChannelKind;
  name: string;
  grade: number | null;
}

export type NoticeStatus = "DRAFT" | "PUBLISHED" | "ARCHIVED";

export interface NoticeCard {
  notice_id: string;
  title: string;
  status: NoticeStatus;
  revision: number;
}

export interface ChatMessage {
  id: string;
  channel_id: string;
  seq: number;
  kind: "TEXT" | "NOTICE_CARD";
  body: string | null;
  author_id: string | null;
  is_mine: boolean;
  notice: NoticeCard | null;
  created_at: string;
}

export interface MessageList {
  items: ChatMessage[];
  next_before: number | null;
}

export interface MessageSend {
  message: ChatMessage;
  replayed: boolean;
}

export interface Notice {
  id: string;
  audience: Audience;
  title: string;
  body: string;
  status: NoticeStatus;
  revision: number;
  can_manage: boolean;
  created_at: string;
  updated_at: string;
  published_at: string | null;
}

export type SourceKind = "OFFICIAL_PUBLIC" | "DEMO";

export interface AcademicTerm {
  id: string;
  name: string;
  starts_on: string;
  ends_on: string;
  source_kind: SourceKind;
}

export interface AcademicEvent {
  id: string;
  title: string;
  starts_on: string;
  ends_on: string;
  source_kind: SourceKind;
  source_url: string | null;
  checked_at: string | null;
}

export interface AcademicEventList {
  term: AcademicTerm;
  items: AcademicEvent[];
}

export type LoadState<T> =
  | { status: "loading" }
  | { status: "error"; error: CampusErrorView }
  | { status: "ready"; data: T };

export interface CampusErrorView {
  title: string;
  detail: string;
  retryable: boolean;
  requestId?: string;
}
