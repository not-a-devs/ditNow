# DIT NOW DB·API 계약 v1.0 초안

본 파일은 구현 전 데이터/인터페이스 계약이다. 실제 DB 마이그레이션이나 애플리케이션 코드를 작성하지 않았다. [DEC-015](../11_DECISION_LOG.md)에 따라 보호 API의 서버 경계는 FastAPI이며 PostgreSQL은 권장 DB 후보이다. [기존 모델](../05_DATA_MODEL.md)의 UUID PK, UTC 시각, role_assignments, 단일 공지 원본, 서버 검증과 DB 채택 시 최소 권한/RLS 설계를 보존한다. 학교 원장에 연결하지 않고 [가상 시연 데이터 계약](../research/07_DATA_PROVENANCE_AND_SEEDS.md)을 따른다.

## 공통 컬럼·제약
모든 저장 레코드는 id, created_at, updated_at, source_kind(OFFICIAL_PUBLIC/DEMO/USER_DEMO), source_url?, checked_at?, revision?, owner_scope를 가진다. 감사 대상 변경은 actor_id, action, entity_id, before/after의 민감정보 제거 요약, timestamp를 audit_logs에 남긴다. 시연 레코드는 실제 학교 공식 배지를 얻을 수 없다. 관계 FK·unique·check 제약과 서버 시간으로 마감/정원을 판정한다. 삭제는 공개 콘텐츠/거래/감사에 따라 soft delete 또는 보존으로 구분하고 실제 보존기간은 OPEN-R14 이후 결정한다.

## 원장과 핵심 관계
| 도메인 | 핵심 테이블과 키 | 필수 상태·무결성 |
|---|---|---|
| 신원/조직 | identities(id,issuer,subject), profiles(user_id), role_assignments(user_id,role,scope), departments(id), academic_memberships(user_id,department_id), academic_terms(id), enrollments(student_id,offering_id) | 검증된 외부 주체→내부 UUID 매핑; 승인 전 소속/역할 비활성; 동일 범위 중복 금지. identities/academic_memberships는 P0 제안 |
| 공지/알림 | notices(id,revision), notice_outbox(notice_id,revision,event), notice_deliveries(notice_id,revision,destination,event), channel_messages(reference_notice_id), notifications(recipient_id,dedupe_key) | draft→published→archived; 원본과 카드 분리; 유일키 멱등 |
| 채팅/익명/팀 | channels(id,scope,kind), channel_memberships(channel_id,user_id), channel_messages(channel_id,client_nonce), anonymous_posts_private(id,author_id), anonymous_posts_public(projection), recruitments(id,owner_id), recruitment_applications(recruitment_id,applicant_id), teams(id) | 기본 채널 유일; 익명 공개 projection 분리; 지원 중복/정원 초과 금지 |
| 기회/취업 | opportunities(id,submission_mode,source_id), saved_opportunities(user_id,opportunity_id), opportunity_check_items(id), career_profiles(user_id), career_consents(user_id,purpose), employer_requests(id) | 외부 제출은 self_reported 상태; 이력서 접근은 동의 범위 |
| 수업/LMS/출결 | course_offerings(id,term_id,section), course_materials(id,offering_id), assignments(id,offering_id), submissions(assignment_id,student_id), course_questions(id), live_sessions(id), learning_units(id), learning_events(id), assessment_attempts(id), attendance_sessions(id), attendance_records(session_id,student_id) | 수강 FK; 제출/진도/시험/대면 출결 원장 분리; 교수 최종 판정 감사 |
| 학사/입학 | academic_requests(id,kind), grades(id,student_id,offering_id), graduation_requirements(id,version), admission_cycles(id,year), applications(id,applicant_id), application_documents(id), admission_decisions(id), tuition_records(id), demo_certificates(id) | 신청→접수→심사→확정 분리; 공식 결제·합격·증명 효력 없음 |
| 도서/공간/생활 | library_titles(id), library_items(id), library_loans(id,item_id,user_id), library_reservations(id), facilities(id), facility_reservations(id,slot), dorm_applications(id), dorm_assignments(id,room_id) | 동일 소장본 활성 대출 1건; 슬롯/방 중복 배정 금지 |
| 지원/공개 | service_requests(id), support_cases(id), case_access_logs(id), public_content(id), content_revisions(id), source_records(id), demo_badges(id) | 고충 별도 접근; 공개 스냅샷 출처/확인일; 가상 배지 명시 |

이 목록은 제품 데이터 모델의 최소 테이블 묶음이다. 기능별 관련 테이블은 [추적표](09_FEATURE_TRACEABILITY.csv)의 db_tables 열을 따른다. 실제 컬럼의 최종 타입·인덱스·보존기간·RLS 문법은 구현 태스크에서 승인된 계약과 함께 버전 관리한다.

## API 공통 계약
인증이 필요한 요청은 FastAPI에서 검증된 세션/토큰으로 user_id를 도출하고 현재 권한 원장을 재조회한다. FastAPI의 Pydantic 입출력 모델과 OpenAPI를 경계 계약으로 사용한다. 성공은 data와 resource_version, server_time; 실패는 code, message, field_errors?, retryable?, request_id를 반환한다. 400 검증, 401 미인증, 403 범위 위반, 404 없음, 409 중복/상태 경합, 429 제한, 5xx 장애를 구별한다. 목록은 cursor/limit과 scope 필터를 가진다. POST/PUT의 중복 위험 작업은 Idempotency-Key를 받거나 자연 유일키로 막는다. 비공개 자원의 403/404 상세는 존재 추론을 막도록 정책화한다.

| 계약 ID | 경로 그룹·동작 | 권한/원장 | 관련 FR |
|---|---|---|---|
| API-ID | /api/v1/session, /profiles, /roles | 본인 세션; 역할 부여 관리자 | AUTH |
| API-HOME | /api/v1/home, /search, /notifications | 본인 권한 집계 | HOME |
| API-NOT | /api/v1/notices, /notices/:id/publish, /notice-deliveries | 작성 범위 검증·outbox | NOT |
| API-CHAT | /api/v1/departments/:id/channels, /channels/:id/messages | 현재 소속/멤버십 | DEPT |
| API-COM | /api/v1/anonymous-posts, /recruitments, /applications, /reports | 공개 projection·소유권 | COM |
| API-OPP | /api/v1/opportunities, /saved-opportunities, /program-applications | 담당 공고/본인 준비 | OPP |
| API-COURSE | /api/v1/offerings, /materials, /assignments, /questions, /live-token | 교수/수강생 | COURSE |
| API-ATT | /api/v1/attendance/sessions, /records, /corrections | 교수/본인 | ATT |
| API-ACA | /api/v1/academic/terms, /registrations, /grades, /requests, /demo-certificates | 학사 범위/본인 | ACA |
| API-ADMIN | /api/v1/admin/roles, /audit, /sources | 범위 관리자 | ADM |
| API-AI | /api/v1/ai/briefings, /summaries | 본인 최소 데이터 | AI |
| API-PUBLIC | /api/v1/public/content, /departments | 게시본 공개; 편집 담당자 | WEB |
| API-ADMIS | /api/v1/admissions/cycles, /applications, /documents, /decisions-demo | 지원자/입학 담당자 | ADMIS |
| API-LMS | /api/v1/learning/units, /events, /attempts | 교수/수강생 | LMS |
| API-LIB | /api/v1/library/titles, /loans-demo, /rooms-demo | 공개/본인/사서 | LIB |
| API-JOB | /api/v1/careers/profiles, /appointments, /employers, /opportunities | 본인 동의/담당자 | JOB |
| API-DORM | /api/v1/dorm/info, /applications-demo | 공개/본인/담당자 | DORM |
| API-HELP | /api/v1/requests, /support-guidance | 민원 본인/담당자; 고충 본문 비활성 | HELP |
| API-CRED | /api/v1/achievements, /badges-demo | 본인/승인 담당 | CRED |
| API-CAMP | /api/v1/campus/buildings, /facilities, /reservations-demo | 공개/본인/시설 담당 | CAMP |

## 연계 이벤트
notice.published→outbox→delivery card→notification; enrollment.changed→채널/강의/파일/라이브 권한 재계산; assignment.due→personal_task; opportunity.published→기회 검색/알림; recruitment.accepted→팀 멤버/채팅; academic_request.approved→학적 반영(가상); live.started→수강생 표시. 이벤트는 원장 commit 후 발행하고 consumer 재시도는 idempotent해야 한다. 검색·알림은 원본 접근 권한을 재검증한다.

## 아직 차단된 계약
실제 SSO/학사/LMS/도서관 동기화, 카드 결제·환불, 공식 증명, 실제 성적 확정, 고충 본문 저장·AI 전송은 API 계약만으로 허용하지 않는다. [미확정 정책](11_OPEN_POLICIES_ASSUMPTIONS.md)과 운영 계약 승인이 선행되어야 한다.


## 기능 추적표의 추가 테이블 등록부
아래 이름도 [추적표](09_FEATURE_TRACEABILITY.csv)의 DB 계약에 속한다. 실제 운영 데이터나 이미 구현된 테이블을 의미하지 않는다.

| 테이블 | 역할 |
|---|---|
| admission_payments | 가상 입학 납부 상태 원장; 실제 결제 없음 |
| ai_usage | 사용자별 AI 요청·비용 한도 집계 |
| anonymous_comments | 익명 댓글 내부 소유 관계; 공개 응답은 작성자 식별자 제외 |
| attendance_change_logs | 교수/담당자 출결 변경 사유·감사 |
| career_appointments | 진로 상담 예약 메타데이터; 민감 본문 분리 |
| department_content | 학과 소개·뉴스·교육과정 출처/개정 |
| dorm_rooms | 시연 생활관 방·정원 원장 |
| learning_achievements | 가상 학습 이수 근거; 공식 인증 아님 |
| notice_attachments | 공지 첨부의 비공개 저장 경로·권한 |
| opportunity_files | 공고 지정 양식의 출처 URL/파일 메타 |
| personal_tasks | 원본 FR ID와 연결된 개인 액션 |
| program_applications | 교내 프로그램 가상 신청/심사 상태 |
| space_bookings | 도서관 그룹실/시네마존 가상 시간 슬롯 예약 |
