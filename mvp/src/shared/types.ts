// 도메인 타입 — docs/05_DATA_MODEL.md 의 테이블을 사전 MVP 범위로 축약한 것.
// 서버(Supabase) 전환 시 같은 이름을 유지해 화면 코드 변경을 최소화한다.

export type Role = 'student' | 'assistant' | 'professor' | 'admin';

export interface Department {
  id: string;
  name: string;
}

export interface User {
  id: string;
  email: string;
  name: string;
  role: Role;
  departmentId: string;
  /** 학생만 의미 있음 */
  academicYear: number | null;
}

/** 클라이언트에 노출 가능한 현재 사용자 정보 */
export type SessionUser = User & { departmentName: string };

export type ChannelKind = 'department' | 'year' | 'free';

export interface Channel {
  id: string;
  departmentId: string;
  academicYear: number | null;
  kind: ChannelKind;
  official: boolean;
  name: string;
  description: string;
  createdBy: string | null;
  createdAt: string;
}

export type MessageKind = 'text' | 'notice_card';

export interface ChannelMessage {
  id: string;
  channelId: string;
  senderId: string | null;
  kind: MessageKind;
  text: string | null;
  referenceNoticeId: string | null;
  noticeRevision: number | null;
  clientNonce: string;
  createdAt: string;
  deletedAt: string | null;
}

export type AudienceType = 'all' | 'department' | 'department_year';
export type NoticeCategory = '학사' | '장학' | '행사' | '취업' | '일반';
export type NoticeStatus = 'published' | 'archived';

export interface Notice {
  id: string;
  authorId: string;
  audienceType: AudienceType;
  departmentId: string | null;
  academicYear: number | null;
  category: NoticeCategory;
  title: string;
  body: string;
  important: boolean;
  status: NoticeStatus;
  revision: number;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
}

export interface NoticeDelivery {
  id: string;
  noticeId: string;
  revision: number;
  channelId: string;
  eventType: 'published' | 'revised';
  createdAt: string;
}

export type PostStatus = 'active' | 'hidden' | 'deleted';

/** 작성자 UID가 포함된 내부 전용 레코드 — 화면에 그대로 내보내지 않는다 */
export interface AnonymousPostPrivate {
  id: string;
  authorId: string;
  title: string;
  body: string;
  status: PostStatus;
  createdAt: string;
  updatedAt: string;
}

export interface AnonymousCommentPrivate {
  id: string;
  postId: string;
  authorId: string;
  body: string;
  status: PostStatus;
  createdAt: string;
}

/** 공개 projection — author_id 없음 (NFR-PRIV-001) */
export interface AnonymousPostPublic {
  id: string;
  title: string;
  body: string;
  createdAt: string;
  updatedAt: string;
  commentCount: number;
  isMine: boolean;
}

export interface AnonymousCommentPublic {
  id: string;
  body: string;
  createdAt: string;
  /** '글쓴이' 또는 '익명1' 처럼 글 안에서만 유효한 번호 */
  alias: string;
  isMine: boolean;
}

export type RecruitmentStatus = 'open' | 'closed' | 'cancelled';
export type ApplicationStatus = 'pending' | 'accepted' | 'rejected' | 'withdrawn';

export interface Recruitment {
  id: string;
  ownerId: string;
  title: string;
  body: string;
  field: string;
  roles: string;
  capacity: number;
  deadline: string;
  status: RecruitmentStatus;
  createdAt: string;
  updatedAt: string;
}

export interface RecruitmentApplication {
  id: string;
  recruitmentId: string;
  applicantId: string;
  message: string;
  status: ApplicationStatus;
  createdAt: string;
}

export type OpportunityKind = '장학금' | '근로' | '공모전' | '취업' | '행사';

export interface Opportunity {
  id: string;
  kind: OpportunityKind;
  title: string;
  organization: string;
  summary: string;
  eligibility: string;
  target: string;
  startsAt: string;
  deadline: string;
  submissionMode: 'external_document_submission' | 'external_link' | 'info_only';
  destination: string | null;
  originalUrl: string | null;
  files: { name: string; url: string | null }[];
}

export type SavedStatus = 'interested' | 'preparing' | 'self_reported_submitted' | 'closed';

export interface SavedOpportunity {
  id: string;
  userId: string;
  opportunityId: string;
  status: SavedStatus;
  memo: string;
  selfReportedSubmittedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface CheckItem {
  id: string;
  savedId: string;
  text: string;
  completedAt: string | null;
  sortOrder: number;
}

export interface Course {
  id: string;
  name: string;
  professor: string;
  room: string;
  departmentId: string;
  slots: { weekday: number; start: string; end: string }[];
}

export interface Enrollment {
  studentId: string;
  courseId: string;
}

export interface Database {
  version: number;
  departments: Department[];
  users: User[];
  channels: Channel[];
  messages: ChannelMessage[];
  notices: Notice[];
  noticeDeliveries: NoticeDelivery[];
  anonPosts: AnonymousPostPrivate[];
  anonComments: AnonymousCommentPrivate[];
  recruitments: Recruitment[];
  applications: RecruitmentApplication[];
  opportunities: Opportunity[];
  saved: SavedOpportunity[];
  checkItems: CheckItem[];
  courses: Course[];
  enrollments: Enrollment[];
}

/** AI 브리핑 출력 스키마 — docs/02_FRD.md FR-AI-001 */
export interface Briefing {
  summary: string;
  actions: { title: string; reason: string; source_type: string; source_id: string }[];
  cautions: string[];
  generatedBy: 'rule' | 'ai';
}
