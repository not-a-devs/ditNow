# 데이터 모델 및 DB 계약 v0.2

> **설계 스키마 초안**. [결정 대장](11_DECISION_LOG.md)의 FastAPI를 서버 경계로 사용하며 2026-10-30 사용자 결정으로 DB는 **MariaDB 확정**이다. 클라우드 접속정보·인증 공급자·DB 계정 권한·비용 조건은 미정이며 실제 연결/마이그레이션은 없다. 실제 학번/성적 데이터는 필요하지 않다.

## 1. 공통 규칙
- 모든 PK는 애플리케이션 UUID, 시각은 UTC, 사용자 노출은 Asia/Seoul 현지화. MariaDB 버전/엔진 확인 후 UUID/시각 물리 타입·정밀도와 연결 시간대를 정한다. PostgreSQL 전용 타입을 전제로 하지 않는다.
- 기본 created_at, updated_at, deleted_at(필요 시). 모든 소유권은 FastAPI에서 검사하고, 채택한 DB의 최소 권한·행 범위 제약으로 추가 보호한다.
- 조직 관계: `departments`, `academic_terms`, `class_cohorts`, `course_offerings`, `enrollments`.
- 사용자 인증: FastAPI가 검증한 `(issuer, subject)`를 제안된 내부 `identities.id` UUID에 매핑한다. 공급자 subject를 UUID라고 가정하지 않는다. 프로필·역할은 내부 ID를 FK로 사용하며 role은 일반 프로필 수정 API로 변경할 수 없다.
- chatbot은 같은 DIT NOW 사용자·로그인 세션·학적 원장을 사용하는 기능이다. 별도 사용자 원장을 생성하거나 기존 standalone 로그인/학생 시드를 최종 플랫폼의 권위로 사용하지 않는다. services/api 중심으로 통합하며 인증 방식·이행 절차는 승인 전 미정이다.
- MVP 외 추후 스키마는 문서상의 모델일 뿐 자동 생성 의무 없음.

## 2. 엔터티/주요 컬럼/제약
| 테이블 | 주요 컬럼(일부) | 제약·설명 |
|---|---|---|
| `identities` (P0 제안) | id, issuer, subject, status | `(issuer, subject)` unique. 검증된 인증 주체만 관리자 시드/승인 절차로 매핑; 자동 역할 부여 금지 |
| `profiles` | user_id, display_name, department_id, academic_year, interest_tags | `identities.id`와 1:1. 소속/학년은 현재 승인된 `academic_memberships`의 읽기 projection이며 편집 가능한 권한 원장이 아님 |
| `academic_memberships` (P0 제안) | user_id, department_id, academic_year, status, valid_from, valid_to | 현재 승인된 active/유효 기간의 소속을 서버 권한 계산에 사용. 실제 학적 연동 아님 |
| `role_assignments` | user_id, role, scope_type, scope_id, granted_by | 동일 범위 역할 중복 unique |
| `departments` | id, name, active | 학과 표준 목록 |
| `academic_terms` | id, year, semester, starts_at, ends_at | 학기 기준 |
| `course_offerings` | id, course_code, term_id, section, professor_id, room | 학기별 분반 unique |
| `enrollments` | student_id, offering_id, status | 학생/분반 unique, 승인된 수강 정보 |
| `timetable_slots` | id, offering_id, weekday, starts_at, ends_at, building_id | 교수/교무 승인한 수업 시간 |
| `attendance_sessions` | id, offering_id, opened_by, opened_at, closed_at | 교수/담당자 전용 |
| `attendance_records` | session_id, student_id, status, finalized_by | 학생×세션 unique, 변경 이력 분리 |
| `notices` | id, author_id, audience_type, audience_id, category, title, body, status, revision | 원본 공지 (단일 진실 공급원) |
| `notice_attachments` | id, notice_id, storage_path, mime, size | 정책 기반 다운로드 |
| `notice_outbox` | id, notice_id, revision, event_type, status, retry_count | 게시 이벤트 재시도 |
| `notice_deliveries` | id, notice_id, revision, destination_type, destination_id, event_type | 고유키로 중복 카드 차단 |
| `channels` | id, department_id, academic_year?, offering_id?, kind, official, created_by | 학과/학년/수업/자유/공식 |
| `channel_memberships` | channel_id, user_id, status | 자유 채널·승인 채널 관리; 기본 소속은 권한 계산 |
| `channel_messages` | id, channel_id, sender_id?, kind, text?, reference_notice_id?, client_nonce | 일반 메시지/공식 카드, nonce unique |
| `anonymous_posts_private` | id, author_id, title, body, status, created_at | **직접 공개 조회 금지**, 소유권 내부 전용 |
| `anonymous_posts_public` | id, title, body, status, created_at | author_id 없는 공개 projection. P0 후보는 별도 읽기 테이블이며 private와 동일 트랜잭션 갱신 |
| `anonymous_comments` | id, post_id, author_id, body, status | 공개 응답에서는 작성자 UID 제외 |
| `reports` | id, reporter_id, target_type, target_id, reason, status | 신고 처리 |
| `realname_activity_profiles` | user_id, display_name, skills, interests, bio | 익명 글과 UI 연결 금지 |
| `recruitments` | id, owner_id, title, body, capacity, deadline, status, opportunity_id? | 주최자 표시, `capacity >= 2`는 모집자 포함 총 정원. 변경 후 `1 + accepted_count ≤ capacity` 보장 |
| `recruitment_roles` | id, recruitment_id, role_name, slots | 모집 역할 |
| `recruitment_applications` | id, recruitment_id, applicant_id, status, message | `(recruitment_id, applicant_id)` unique |
| `opportunities` | id, publisher_id, kind, title, body, target, deadline, submission_mode, destination, original_url | 원본 출처/외부 제출 안내 |
| `opportunity_files` | id, opportunity_id, storage_path/original_url, filename | 지정 양식 |
| `saved_opportunities` | id, user_id, opportunity_id, status, self_reported_submitted_at | `(user_id, opportunity_id)` unique |
| `opportunity_check_items` | id, saved_opportunity_id, text, completed_at, sort_order | 개인 체크리스트 |
| `course_notices` | id, offering_id, notice_id | 강의 공지 원본 연결 |
| `course_materials` | id, offering_id, uploaded_by, filename, storage_path, mime, size | 수강생 범위 read |
| `assignments` | id, offering_id, created_by, title, instructions, due_at, status | 분반별 과제 |
| `submissions` | id, assignment_id, student_id, storage_path, status, submitted_at | 학생별 제출 권한 |
| `course_questions` | id, offering_id, author_id, body, visibility, status | 질문 전용함 |
| `course_answers` | id, question_id, professor_id, body | 교수 공식 답변 |
| `live_sessions` | id, offering_id, host_id, provider_room_id, status, started_at, ended_at | 학생 접근 토큰 서버 발급 |
| `personal_tasks` | id, user_id, title, due_at, status, source_type, source_id | 통합 액션 센터 |
| `notifications` | id, recipient_id, type, entity_type, entity_id, read_at, dedupe_key | recipient + dedupe unique |
| `ai_usage` | user_id, date, requests_count, tokens_estimate | 제한 집계 |
| `audit_logs` | actor_id, event, entity_type, entity_id, timestamp, metadata_redacted | 승인·권한·출결 등. 익명 글 actor↔공개 글 연결은 일반 감사 조회에서 제외하고 제한된 별도 절차로 격리 |

## 3. 도메인 불변식
1. 공식 공지는 `notices.id`가 원본이고 채팅 카드는 `reference_notice_id`만 가진다.
2. 학과 기본 채널 `(department_id, kind=all)` 및 `(department_id, academic_year, kind=year)`는 유일하다.
3. 사용자 소속은 스스로 설정/변경만으로 인증되지 않는다; 서버/관리자 프로비저닝.
4. 실명 모집 참여 인원은 모집자 1명+승인 지원자 수이며 `1 + accepted_count ≤ capacity`다. 화면만 검사하지 않고 지원 승인·정원 수정이 같은 DB 트랜잭션 잠금 규약으로 검증한다.
5. 익명 글의 소유자 UID가 일반 학생에 대한 SELECT 응답으로 유출되지 않도록 공개 전용 view/function 경로를 사용한다.
6. 외부 장학금의 `self_reported_submitted_at`은 학생이 입력한 기록일 뿐 해당 기관 접수 사실의 증거가 아니다.
7. 제출/수정은 서버 `NOW()`와 마감 정책으로 처리한다.

## 4. 인덱스·동시성·MariaDB 최소 권한 계약
- `notices(status, published_at desc)`, `(audience_type,audience_id)`
- `channel_messages(channel_id,created_at desc)`, `notifications(recipient_id,created_at desc)`
- `recruitments(status,deadline)`, `opportunities(kind,deadline)`, `saved_opportunities(user_id,opportunity_id)` unique
- `enrollments(student_id,offering_id)` unique, `recruitment_applications(recruitment_id,applicant_id)` unique
- FastAPI가 검증한 현재 사용자·역할·소속으로 보호 API의 접근을 판정하고 MariaDB 질의에도 소유자·대상·부모 범위를 포함한다. PostgreSQL RLS/auth.uid/SET LOCAL을 현재 권한 구현 수단으로 전제하지 않는다.
- MariaDB 런타임 DB 계정에는 필요한 테이블·컬럼·업무만 GRANT하고 스키마/계정 관리 권한과 분리한다. 관리자 쓰기·익명 신원 매핑·워커의 별도 계정/제한 view·루틴은 검토 후보이며 승인 없이 생성하지 않는다. DB 자격 증명은 브라우저/chatbot 사용자 입력에 전달하지 않는다. [공식 GRANT](https://mariadb.com/docs/server/reference/sql-statements/account-management-sql-statements/grant)·[view 권한 문맥](https://mariadb.com/docs/server/server-usage/views/create-view) 확인일: 2026-10-30.
- `notice_outbox`는 재시도 시 상태/시도횟수와 다음 시도시각 업데이트, 이미 생성된 `notice_deliveries`는 중복 삽입 불가.

## 5. 데이터 시드 (시연 전용)
- 학교 관리 계정 1, 조교 계정 1, 교수 계정 1, 같은 학과·학년 학생 2, 다른 학과 학생 1.
- 학과 2개, 학년 2개, 강의실 1~2개, 공지 2개, 장학금 양식 예시 1, 공모전 모집 1.
- 로그인 정보는 저장소 비밀값 제외 정책에 맞춰 별도 심사 경로 전달.
- 화면에 **가상 데이터 / 본 해커톤 신규 시스템** 표기. 실제 학생 이름/학번 사용 금지.
