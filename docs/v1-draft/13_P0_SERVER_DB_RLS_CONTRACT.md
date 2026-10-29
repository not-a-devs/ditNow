# DIT NOW P0 서버·MariaDB 권한 계약 초안

> TASK-04 · 원안 2026-10-29 / 사용자 결정 반영 2026-10-30 · 상태: **FastAPI·MariaDB 확정 / 인증·클라우드 접속·권한·비용 조건 승인 대기**. 이 문서는 FastAPI API와 MariaDB의 최소 권한·스코프 질의 구현 입력을 구체화한다. 실제 인증/업무 API, DB 연결, 정책, 마이그레이션 또는 학교 연동을 구현한 기록이 아니다. 파일명의 RLS는 기존 참조 보존용이며 PostgreSQL RLS를 현재 요구로 삼지 않는다.

## 1. 범위와 우선순위

기존 92개 [기능 추적표](09_FEATURE_TRACEABILITY.csv) 가운데 P0인 FR-AUTH-001/002, FR-COM-001/004, FR-OPP-004를 먼저 연결한다. FR-COM-005(지원·승인)는 P1이지만 P0 모집 원장의 FK와 정원 제약을 미리 정한다. 공고 원본 FR-OPP-001~003은 P1이며 P0 개인 준비를 시연하려면 관리자 승인 **가상 공고 시드**가 선행된다. 학과·학년 관계는 FR-DEPT-001~008과 공지 대상 권한의 공통 입력이다. 이 문서는 기존 [DB·API](05_DB_API.md), [RBAC](04_RBAC.md), [아키텍처](06_ARCHITECTURE.md), [미확정 정책](11_OPEN_POLICIES_ASSUMPTIONS.md)의 세부 계약이며 DEC-001~014를 변경하지 않는다.

사용자 확정(2026-10-30): `mvp/`는 사전 프로토타입으로 격리하며 최종 시연·제출·소스 복사에 사용하지 않는다. 프런트는 `apps/web/`에서 새로 작성하고 `services/api/`를 공통 서버 경계로 사용한다. chatbot은 DIT NOW 내부 기능으로 공통 사용자·로그인 세션·학적 원장을 사용하며 독립 사용자 시스템을 만들지 않는다. 기존 standalone 로그인은 최종 통합에서 대체한다. 이 계약의 서버 권한·DB 불변식·다중 계정 격리는 **미구현**이다.

## 2. 착수 게이트와 기술·비용 확인

| 항목 | 확인 결과와 처리 |
|---|---|
| 확정된 기술 | [DEC-015](../11_DECISION_LOG.md): React/Vite/Tailwind 프런트엔드와 FastAPI 백엔드. DFLT-001의 Supabase/Edge Functions/Vercel 구상은 더 이상 기본 스택이 아니다. `/api/v1`은 FastAPI의 논리 라우트 계약이다. |
| DB 확정 | 2026-10-30 사용자 결정으로 **MariaDB**를 사용한다. 클라우드 인스턴스 예정이며 접속정보·버전·계정 권한은 없다. DB 제품 선택 차단은 해제되었으나 연결/마이그레이션은 미실행이다. |
| 프로젝트 권한·비용 | 팀 소유 계정, 프로젝트 생성 권한, 리전, 청구 방식, 무료 한도 초과 정책, 비밀키 보관 담당자, 배포 권한은 **미확인**. 새 서비스 개설·유료 플랜·실제 데이터 입력은 하지 않는다. |
| 인증 결정 | 가상 시연 계정의 관리 책임자 OPEN-003이 미결정이다. 공개 회원가입은 기본 거부하고 승인된 가상 계정 시드만 허용하는 설계 후보로 둔다. 학교 SSO·운영 DB·실제 학생 확인은 범위 밖이다. |
| 착수 상태 | FastAPI/Pydantic/OpenAPI와 MariaDB용 논리 계약 검토는 가능하다. 실제 인증/DB 연결·계정 생성은 OPEN-002/003의 남은 인증·접속정보·자격 증명 소유자·테스트 환경·비용 한도를 승인한 뒤 별도 PR에서 진행한다. |

## 3. 공통 API 형식

- HTTPS `/api/v1`; FastAPI의 인증 의존성이 선택된 공급자의 주체를 검증한다. JWT 채택 시 서명·만료·발급자·대상을 검증하고, 불투명 세션 채택 시 서버 측 조회·만료·폐기를 검증한다. 검증된 `(issuer, subject)`를 승인된 내부 UUID로 매핑한다. Pydantic 모델로 입력을 검증하고 응답 모델로 공개 필드를 제한한다. 인증 방식 자체는 OPEN-002다. 본문·쿼리의 `user_id`, `role`, `department_id`, `academic_year`를 권한의 증거로 사용하지 않는다.
- JWT를 채택하면 서버 설정의 정확한 issuer·audience·서명 알고리즘·고정된 키/JWKS 위치 허용목록을 검증한다. 토큰의 `jku`/`x5u` 등 동적 키 URL이나 임의 issuer를 신뢰하지 않는다. issuer/subject를 임의로 정규화해 다른 주체와 합치지 않는다. 미등록 주체는 401로 거부하고 identities/역할을 자동 생성하지 않는다. 이메일 일치만으로 기존 학생·교직원·관리자 계정에 자동 연결하지 않는다. 초대·사전 프로비저닝·바인딩/재연결 절차는 OPEN-002/003 승인 전 차단한다.
- 요청 Pydantic 모델은 생성/수정별 허용 필드를 명시하고 `extra='forbid'`로 알 수 없는 필드를 거부한다. `owner_id`, `author_id`, 역할·소속 승인값, `source_kind`, 서버 revision·시각은 클라이언트 입력으로 대량 할당하지 않는다. 자원 상태 변경도 허용된 업무 입력만 받으며, 선택 공고 ID의 공개/대상 권한은 서버가 다시 확인한다.
- 성공: `{ data, resource_version, server_time }`; 목록은 `{ data, next_cursor, server_time }`. 실패: `{ code, message, field_errors?, retryable, request_id }`. `server_time`은 UTC ISO 8601, 식별자는 UUID. 공개 문자열 입력은 정규화·길이 제한·출력 이스케이프를 적용한다.
- 400 필드 검증, 401 세션 부재/만료, 403 승인 범위 밖, 404 없는 자원, 409 중복·버전·상태 경합, 429 요청 제한, 5xx 장애. 비공개 자원은 타인 소유와 부재를 구별할 수 없도록 외부에는 404로 정규화하고 내부 감사에는 사유 코드를 남긴다.
- 기존 자원의 수정·삭제 및 상태 변경은 `If-Match: <resource_version>`으로 기대 버전을 전달하고 서버가 변경과 함께 원자적으로 비교한다. 필수 버전 누락은 400, 불일치는 409다. 멱등 키는 버전 검사를 대신하지 않는다. 생성·지원 승인 등 중복 위험 동작은 별도로 `Idempotency-Key`를 받는다. 목록은 불투명 cursor와 제한된 `limit`을 사용한다.
- 멱등 기록의 유일 범위는 `(내부 actor_id, HTTP method, 정규화된 대상 경로, Idempotency-Key)`다. 본문과 조건부 헤더의 해시를 함께 저장하고 같은 범위·같은 요청 재시도에만 이전 결과를 돌려준다. 같은 키에 다른 요청은 409다. 인증·현재 역할/소속·자원 권한을 **저장 응답 재생 전에도** 검증하며, 권한을 잃은 요청에는 이전 결과를 노출하지 않는다. 동시 동일 키는 원자적으로 한 실행만 허용하고, 완료된 동일 요청의 재생은 최초 기대 버전으로 실행된 결과를 반환한다. TTL·진행 중 요청의 재시도 응답·실패 결과 저장 범위는 구현 전 계약으로 확정할 항목이며 아직 정하지 않았다. 멱등 기록에 토큰·비밀번호·익명 작성자 연결값을 넣지 않는다.
- 파일·외부 URL·공지 공식성은 별도 원장/권한의 결과다. 시연 레코드에는 `source_kind=DEMO|USER_DEMO`를 반환하고 실제 제출·학교 확인 상태처럼 표시하지 않는다.
- `is_mine` 등 사용자별 익명 응답은 공유 캐시에 저장하지 않고 `Cache-Control: private, no-store`를 적용한다. 사용자별 값이 다른 응답을 CDN·프록시에서 재사용하지 않으며 선택 인증 방식의 Authorization/Cookie 차이를 반영한다. 실시간 payload도 허용된 공개 projection으로 제한한다. 타임스탬프 절삭은 확정 정책이 아니다.

## 4. P0 원장과 무결성

아래는 MariaDB 대상 논리 스키마다. ID는 애플리케이션 UUID, 시각은 UTC, 변경 가능한 행은 양수 revision을 사용한다. UUID 저장 형식·시각 컬럼의 물리 타입/정밀도·엔진·인덱스·migration은 클라우드 MariaDB 버전과 트랜잭션/FK 지원을 확인한 뒤 별도 리뷰한다. PostgreSQL의 uuid/timestamptz 문법을 그대로 적용하지 않는다. FK 삭제는 기본 제한, 공개 콘텐츠 삭제는 상태 전이와 감사 기록으로 처리한다. 특정 인증 공급자의 스키마를 전제하지 않는다.

| 테이블 | 필수 필드와 FK/유일성 | 소유·상태 불변식 |
|---|---|---|
| `identities` **신규 제안** | `id`(내부 UUID PK), `issuer`, `subject`, `status`, `(issuer,subject) UNIQUE` | 플랫폼과 chatbot이 공유하는 신원 원장. 공급자 subject의 형식을 가정하지 않는다. 검증된 주체를 승인된 내부 ID에만 매핑; 미등록/비활성 주체는 401. 로그인 비밀은 여기에 저장하지 않는다. |
| `profiles` | `user_id PK/FK → identities.id`, `display_name`, `status`, `source_kind` | 내부 사용자 ID와 1:1. 가상 프로필만 P0. 이메일·로그인 비밀은 별도 인증 원장; 공개 모집 응답에 이메일 없음. |
| `departments` | `id`, `code UNIQUE`, `name`, `source_url?`, `checked_at?` | 공개 확인 자료와 가상 시드 구분. 코드 미확정이면 운영 공식 코드로 가장하지 않음(OPEN-R10). |
| `academic_memberships` **신규 제안** | `id`, `user_id FK`, `department_id FK`, `academic_year > 0?`, `term_id?`, `status`, `valid_from`, `valid_to?` | 승인된 현재 소속 한 건을 권위로 사용. 휴학·전과·기간 만료 시 권한 재평가. 학년 상한·학제는 미확정이며 시연 속성일 뿐 실제 학적 아님. P0에서 `profiles.department_id/year`는 읽기 projection일 뿐 권한 원장 아님. |
| `role_assignments` | `id`, `user_id FK`, `role`, `scope_type`, `scope_id?`, `status`, `valid_from/to` | `(user_id,role,scope_type,scope_id,유효 기간)` 중복 금지. 관리자 승인 트랜잭션만 변경; 일반 사용자의 직접 INSERT/UPDATE/DELETE 금지. |
| `anonymous_posts_private` | `id`, `author_id FK`, `title`, `body`, `status`, `revision` | 작성자 매핑은 비공개. `active→hidden/deleted`, 복구는 신고 정책 승인 이후. 작성자만 자기 글 수정/삭제, 운영자 조치는 감사 필수. |
| `anonymous_posts_public` | `id FK`, `title`, `body`, `status`, `created_at/updated_at`, `comment_count` | **별도 공개 읽기 모델**. `author_id`, 이메일, 학과, 학년, 작성자와 연결 가능한 안정 식별자를 두지 않는다. 비공개 원장과 동일 트랜잭션에서 갱신. 공개 조회에서 private 테이블에 join하지 않는다. |
| `recruitments` | `id`, `owner_id FK`, `opportunity_id FK?`, `title`, `body`, `field`, `roles`, `capacity`, `deadline_at`, `status`, `revision` | 실명 활동 프로필만 노출. 기존 데이터 모델에 따라 `capacity ≥ 2`는 **모집자 포함 총 인원**. 정원 변경도 모집 행 잠금 안에서 `capacity ≥ 1 + accepted_count`를 검증한다. `open→closed/cancelled`; 서버 시각으로 마감 판정. 외부 공고 연결은 원본 ID만 사용. 삭제 전이와 지원 이력 처리는 아래 승인 대기 후보다. |
| `recruitment_applications` | `id`, `recruitment_id FK`, `applicant_id FK`, `message`, `status`, `created_at` | `(recruitment_id,applicant_id)` 유효 지원 중복 금지. 모집자 자기 지원 금지. `pending→accepted/rejected/withdrawn`; 승인 시 행 잠금/트랜잭션으로 `1 + accepted_count ≤ capacity` 보장. P1 UI 전에도 스키마 제약 정의. |
| `opportunities` | `id`, `kind`, `title`, `organization`, `eligibility`, `target_scope`, `deadline_at`, `submission_mode`, `destination?`, `original_url?`, `source_kind`, `source_url?`, `checked_at?`, `status` | P0는 관리자 승인 가상 시드만 읽음. `external_document_submission|external_link|info_only` 구분; 원문 없는 시연 공고는 DEMO 표시. |
| `saved_opportunities` | `id`, `user_id FK`, `opportunity_id FK`, `status`, `memo`, `self_reported_submitted_at?`, `revision` | `(user_id,opportunity_id) UNIQUE`. `interested→preparing→self_reported_submitted/closed` 기본 흐름. 실수 정정은 본인 요청과 감사 기록으로 허용하되 외부 접수 확인으로 승격 불가. |
| `opportunity_check_items` | `id`, `saved_id FK`, `text`, `sort_order`, `completed_at?`, `revision` | 부모 저장 항목의 본인만 CRUD. 항목 순서/완료를 서버가 원자적으로 갱신. |

`academic_memberships` 추가는 기존 `profiles`·`role_assignments`·`enrollments`의 의미를 바꾸지 않기 위한 제안이다. chatbot도 동일 원장의 승인 소속/수강을 조회하며 별도 학적 복제를 권위로 삼지 않는다. 실제 테이블명·학기 모델은 승인 전 변경 가능하다. 익명 공개 모델은 별도 읽기 테이블 후보이며 비공개 원장과 원자 갱신한다. MariaDB view를 선택한다면 [공식 view 문서](https://mariadb.com/docs/server/server-usage/views/create-view)의 DEFINER/INVOKER 권한 문맥을 별도 검토한다. view가 앱 사용자의 신원을 자동 검증한다고 가정하지 않는다. 확인일: 2026-10-30.

소속 상태 후보는 `pending|active|inactive`; 권한은 `active`이고 유효 기간 안인 기록만 인정한다. `role_assignments.scope_type` 후보는 `platform|department|course_offering`이며 역할은 기존 학생·교수·조교·관리자 유형을 사용한다. 한 사용자에게 유효한 주 소속이 겹치지 않도록 DB 제약 또는 직렬화 트랜잭션으로 막는다. 학과 코드/학년별 기간·교직원 다중 소속·학기 변경 규칙은 학교 정책으로 확정하지 않고 OPEN-003/OPEN-R10에 남긴다.

## 5. 동작별 API 계약

모든 본문/응답은 FastAPI 라우트·Pydantic 모델 설계 후보이며 기존 mock API의 호출 방식과 자동으로 호환된다는 뜻이 아니다. 응답은 위 공통 래퍼를 생략해 표시한다. 공개 OpenAPI에서 비공개 작성자 필드가 나타나지 않도록 응답 모델을 분리한다.

| 계약·FR/TC | 메서드/경로 | 요청 → 응답·저장 | 권한·주요 실패 |
|---|---|---|---|
| API-ID · FR-AUTH-001 · TC-V1-AUTH-001 | `GET /session`, `POST /session/logout` | 검증된 주체 매핑 → 본인 내부 `user_id`, 승인 역할·현재 소속·`source_kind`; 로그아웃은 선택된 공급자/세션 방식의 종료 결과 | 미등록·비활성·만료 401. 인증 발급/갱신 방식은 공급자 선택 후 명세; 클라이언트 전송 ID로 세션 생성 금지. |
| API-ID · FR-AUTH-002 · TC-V1-AUTH-002 | `GET /me/affiliation`, `POST /admin/demo-affiliations`, `PATCH /admin/demo-affiliations/{id}` | 관리자 입력: 가상 대상 ID·학과·학년·역할·유효 기간·사유 → 승인된 소속/역할 revision | 승인 관리자만 변경, 본인 승격 403, 잘못된 FK 400, 중복/겹침 409; 감사 기록. OPEN-003 승인 전 관리자 쓰기 API 배포 금지. |
| API-COM · FR-COM-001 · TC-V1-COM-001 | `GET /anonymous-posts`, `GET /anonymous-posts/{id}`, `POST /anonymous-posts`, `PATCH /anonymous-posts/{id}`, `DELETE /anonymous-posts/{id}` | 제목·본문 → 공개 글(작성자 식별 필드 없음), 본인 여부는 `is_mine` boolean으로만 계산; create/update/delete와 공개 모델 원자 갱신 | 승인된 가상 학생; 자기 글만 변경. 타인 수정 404, 버전 충돌 409, 비활성 글 공개 조회 404. |
| API-COM · FR-COM-004 · TC-V1-COM-004 | `GET /recruitments`, `GET /recruitments/{id}`, `POST /recruitments`, `PATCH /recruitments/{id}`, `POST /recruitments/{id}/close` | 제목·본문·분야·모집 역할·총 정원·마감·선택 공고 ID → 실명 활동 프로필/상태/revision | 승인된 가상 학생; 모집자만 변경. 최소 정원 미만 400, 현재 승인 인원보다 정원 축소·버전/마감/종료 경합 409, 타인 변경 404. 정원·마감·종료도 지원 승인과 같은 모집 행 잠금 사용. 학생 이메일은 응답 제외. |
| API-COM · FR-COM-004 · TC-V1-COM-004 | **승인 대기 후보:** `DELETE /recruitments/{recruitment_id}` | 본인 삭제 요청 + 기대 버전 → 논리삭제와 공개 목록/상세 제외 후보; 물리삭제·지원 이력 제거 없음 | **BLOCKED_POLICY:** 삭제 후 복구/보존 및 지원 이력이 있는 모집의 취소·지원자 고지 정책이 미정이다. 해당 정책 승인 전 삭제 API를 활성화하지 않는다. 모집 CRUD 요구는 유지하며 종료를 삭제 완료로 간주하지 않는다. |
| API-COM · FR-COM-005 · TC-V1-COM-005 | `POST /recruitments/{recruitment_id}/applications`, `POST /recruitments/{recruitment_id}/applications/{application_id}/decision`, `POST /recruitments/{recruitment_id}/applications/{application_id}/withdraw` | 지원 메시지 → 지원 상태; 결정 `accept|reject` → 팀 인원/상태 | **P1, P0 공개 UI 범위 밖**. 본인 지원/철회, 모집자 승인; 해당 지원의 부모 모집 FK까지 확인하며 불일치는 404. 중복·마감·정원 초과 409. 멱등 키와 행 잠금 필수. |
| API-OPP · FR-OPP-004 · TC-V1-OPP-004 | `GET /me/saved-opportunities`, `PUT /me/saved-opportunities/{opportunity_id}`, `PATCH /me/saved-opportunities/{opportunity_id}`, `DELETE /me/saved-opportunities/{opportunity_id}` | 공고 ID, 준비 상태·메모 → 본인 저장 항목/revision; PUT 반복은 동일 레코드 반환 | 현재 세션 본인만. 없는/비공개 공고 404, 버전 경합 409. 삭제는 본인 체크 항목과 함께 처리; 감사/보존 정책은 OPEN-009. |
| API-OPP · FR-OPP-004 · TC-V1-OPP-004 | `POST /me/saved-opportunities/{opportunity_id}/checks`, `PATCH /me/saved-opportunities/{opportunity_id}/checks/{id}`, `DELETE /me/saved-opportunities/{opportunity_id}/checks/{id}` | 체크 문구·순서·완료 여부 → 갱신된 항목/revision | 항목의 부모 소유권까지 확인. 타 계정 항목 404, 중복 요청 멱등, 정렬 충돌 409. |

`POST /session/login`의 실제 자격 증명·토큰 교환은 인증 공급자 채택 시 FastAPI 어댑터/공급자 계약으로 정의한다. FastAPI 자체가 로그인·세션 저장소를 자동 제공한다고 가정하지 않는다. 기존 시연용 이메일/비밀번호를 운영 인증으로 이관하지 않는다. 실명 모집 프로필은 `profiles`의 허용된 필드만 반환한다. 익명 글과 실명 모집 사이에 공개 작성자 연결 API는 없다.

## 6. FastAPI 권한과 MariaDB의 DB 방어선

**FastAPI의 필수 책임:** 인증 의존성에서 유효한 주체를 확인하고, 서비스/라우트에서 현재 승인 역할·소속·소유권·자원 상태를 매 요청 판정한다. 401/403/404를 구별해 외부 응답은 존재 추론을 막는다. Pydantic 입력 검증, 공개 응답 필터, 감사·남용 제한, 관리자 승격 승인도 서버 책임이다. 오래된 토큰의 role·학과·학년 claim은 권한 원장 대신 사용하지 않는다. [FastAPI 공식 보안 안내](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)의 의존성/JWT 예시는 구현 참고이며 특정 인증 공급자를 결정한 근거가 아니다.

**MariaDB의 추가 책임:** 스키마 관리 계정과 런타임 DB 계정을 분리하고 필요한 테이블·컬럼·작업만 GRANT한다. 런타임에 전역/관리 권한이나 GRANT OPTION을 부여하지 않는다. MariaDB는 테이블/컬럼/루틴 수준 권한을 제공한다([GRANT 공식 문서](https://mariadb.com/docs/server/reference/sql-statements/account-management-sql-statements/grant), 2026-10-30 확인). 이것만으로 플랫폼 사용자별 행 접근이 자동 제한되지는 않는다. FastAPI의 객체별 인가와 권한 범위가 포함된 매개변수화 질의를 필수로 사용하며 조회/삽입/수정/삭제별 교차 계정 테스트를 수행한다.

**주체 전달 경계:** 브라우저·chatbot의 사용자 입력에 DB 직접 연결이나 신뢰할 사용자 ID 전달을 허용하지 않는다. services/api가 검증한 공통 세션에서 내부 사용자·현재 소속을 도출하고 자원/부모 소유권 조건을 질의에 적용한다. 누락된 주체·범위는 기본 거부하며 연결 풀 재사용, 우회 질의, SQL 주입을 테스트한다. 과거 PostgreSQL/Supabase 구상의 `auth.uid()`, `SET LOCAL`, `BYPASSRLS` 또는 행 정책을 MariaDB의 현재 준수 수단으로 사용하지 않는다. DB 세션 변수나 루틴 인수에 담긴 UUID는 독립된 신원 증명이 아니다.

**익명 부수 저장소 경계:** 감사·접근 로그, 멱등 레코드/응답, rate-limit 키, 분석·백업도 작성자↔공개 글 ID의 제2 원장이 될 수 있다. 일반 감사 담당자의 권한으로 두 값을 결합해 조회할 수 없어야 한다. 일반 로그/감사에는 익명 요청의 actor와 원시 글 경로/식별자를 함께 남기지 않으며 토큰·본문도 제외한다. 업무상 필요한 연결은 비식별화 또는 제한된 별도 저장소·접근권으로 격리한다. 격리 구현·복호/가명화 키 책임자·보존/삭제/백업 절차는 OPEN-009와 익명 신고 접근 절차 승인 후 정한다. 익명 멱등 저장소의 사용자 범위 격리는 필요하지만 일반 감사/로그 역할의 조회 허가는 아니다.

**DB 권한 분리 추가 검토:** 일반 앱 읽기/쓰기, 역할·소속 승인, 익명 신원 조회, outbox 업무가 단일 자격 증명에 모두 묶이면 한 경로의 SQL 오용이 넓은 권한으로 이어진다. 별도 DB 계정·연결 풀·제한된 view/루틴 후보를 검토하고 자격 증명·실행권·스키마 참조를 승인한 뒤 구현한다. MariaDB 루틴의 `SQL SECURITY DEFINER|INVOKER`와 EXECUTE 권한은 [공식 문서](https://mariadb.com/docs/server/reference/sql-statements/data-definition/create/create-function)에 있다(2026-10-30 확인). 권한상승 문맥의 루틴에서 전달받은 `p_user`만 비교하는 방식은 신원 위조 해결책이 아니다. 구체 루틴·계정·뷰 선택은 아직 미확정이다.

다음 표는 **FastAPI를 통한 최종 사용자별 유효 접근**을 나타낸다. 각 열의 학생·관리자는 MariaDB 로그인 계정을 뜻하지 않는다. DB 권한과 스코프 질의·뷰/루틴은 클라우드 연결/계정 권한 승인 후 별도 명세한다.

| 자원 | 공개/미인증 | 승인 학생 | 모집자·작성자 | 관리자/운영자 |
|---|---|---|---|---|
| `identities`, `profiles`, `academic_memberships`, `role_assignments` | 없음 | 본인 최소 프로필 projection 조회; identity/역할·소속 직접 쓰기 불가 | 동일 | 승인 범위의 변경만 서버 전용 절차 + 감사. OPEN-003 전 쓰기 비활성 |
| `anonymous_posts_private` | 없음 | **테이블 직접 접근 불가** | 서버 전용 작성/수정/삭제 경로에서 소유권 확인 | 별도 신고 승인 경로만; 일반 관리자 전체 신원 조회 금지 |
| `anonymous_posts_public` | 없음 | 활성 글만 SELECT, 직접 쓰기 불가 | `is_mine`은 서버에서 계산 | 운영 조치는 비공개 원장에 기록 후 공개 모델 갱신 |
| `recruitments` | 없음 | 공개 모집 SELECT/본인 INSERT | 본인 UPDATE/종료 | 허가된 조치만 감사 기록 |
| `recruitment_applications` | 없음 | 본인 지원/철회/조회 | 본인 모집의 지원 조회·결정 | 일반 관리자 기본 거부 |
| `opportunities` | 출처가 허용한 공개 정보만 별도 공개 projection | 공개/대상 공고 SELECT | 동일 | 승인 담당자만 공고 쓰기(P1) |
| `saved_opportunities`, `opportunity_check_items` | 없음 | FastAPI가 검증한 현재 사용자와 행/부모 소유를 대조해 CRUD; MariaDB 질의에도 같은 소유/부모 범위 조건 적용 | 동일 | 일반 관리자 기본 거부; 복구는 별도 승인 절차 |

**컬럼 노출·view 권한 문맥·루틴 실행권**은 FastAPI 인가와 별도로 검토한다. 익명 private/public 간 공개 join, `author_id`가 담긴 실시간 payload, 역할 변경을 허용하는 넓은 `UPDATE`, DB 관리자 자격 증명·인증 비밀값의 클라이언트 노출은 차단 이슈다. 익명 댓글은 FR-COM-002의 P2이므로 이 계약에서 별도 공개 원장/별칭을 구현 완료로 간주하지 않는다.

## 7. 상태 전이·이벤트·동시성

1. 승인된 가상 소속/역할 변경은 한 트랜잭션에서 기존 유효 기간 종료→신규 기록→감사 기록. 변경 후 API·채팅·공지·파일 조회가 새 DB 소속을 사용하도록 재검증한다. 열린 실시간 연결은 권한 변경 이벤트 또는 재인증으로 끊고, 실패 시 짧은 재검증 주기를 둔다.
2. 익명 작성/수정/삭제는 private 행과 public 읽기 모델을 원자적으로 갱신한다. 삭제한 글의 공개 검색/캐시도 제거한다. 공개 응답·로그·오류·분석에 작성자 ID를 내보내지 않는다.
3. 모집 지원 승인에는 모집 행 잠금→현재 권한·기대 버전·마감/상태 재검사→승인 인원 계산→지원 상태 갱신→팀 멤버 반영 순서를 사용한다. 모집 정원·마감·종료 변경 및 지원 철회도 같은 모집 행 잠금 규약을 따르고, 정원 축소는 `new_capacity ≥ 1 + accepted_count`를 만족해야 한다. 두 동시 승인이나 정원 변경과 승인이 경합해도 정원을 초과하지 못한다. 지원 이벤트/알림은 commit 후 outbox로 발행한다. 모집 삭제와 지원 이력의 관계는 위 BLOCKED_POLICY를 해소한 뒤 정의한다.
4. 개인 기회 `self_reported_submitted`는 사용자의 자체 기록이다. 외부 기관 제출 확인 이벤트나 공식 합격/장학 확정으로 변환하지 않는다. 홈/알림은 원본 공고 ID와 개인 저장 ID를 참조하고 조회 시 권한/출처를 다시 확인한다.

## 8. 수용 테스트와 미해결 결정

| 관련 NFR | 이 계약에서의 검증 지점 |
|---|---|
| NFR-SEC-001~006 | 서버 세션 검증, DB 범위 권한, 관리자 승격 제한, 비밀키 비노출, 입력 검증, 429 제한 |
| NFR-PRIV-001~003 | 익명 공개 모델의 식별자 배제, 가상 최소 데이터, 감사 로그 접근 제한 |
| NFR-REL-001/003/004/005 | 서버 영속성, 지원 정원 원자성, 네트워크 오류 복구, cursor 목록 |
| NFR-DATA-001~003 | 원본/개인 상태 분리, 외부 제출 자기 보고, FK·unique·서버 시각 |
| NFR-OPS-001~004 | 승인 후 재현 가능한 migration·환경 예시·테스트 증거·비밀정보 배제. 이 PR에는 migration/운영 비밀값 없음 |

| 테스트 | 필수 증거·완료 조건 |
|---|---|
| TC-V1-AUTH-001/002 | 가상 학생 A/B와 관리자 계정으로 로그인·만료·로그아웃·역할 승인/자기 승격 거부; 소속 변경 직후 옛 학과 API·채팅·파일 거부. DB 원장과 감사 행 확인. |
| TC-V1-COM-001, TC-V1-X02 | A 익명 글 생성/수정/삭제 후 B 조회; B·미인증자의 타인 변경 거부; 공개 JSON·검색·실시간·로그에 `author_id`/이메일/소속이 없음. 일반 감사/로그 권한으로 감사·멱등·rate-limit·분석·백업을 통해 작성자와 공개 글을 결합할 수 없음. A의 `is_mine` 응답이 B에게 공유 캐시로 재생되지 않음. 새로고침·재로그인에도 원장 일치. |
| TC-V1-COM-004/005 | A 실명 모집과 공고 원본 연결; B 지원, A 승인, C 동시 승인에서 총 정원 초과 없음. 정원 축소와 승인 경합·승인 인원보다 작은 정원 거부·다른 모집에 속한 지원 ID 404를 검증. A 프로필은 허용 필드만 노출하고 익명 글과 연결되지 않음. 삭제는 정책 승인 전 비활성, 승인 후 공개 제외/지원 이력 처리 테스트 필요. P1 지원 UI 미구현이면 해당 테스트 NOT_RUN. |
| TC-V1-OPP-004, TC-V1-X03 | A 공고 저장·상태·체크 수정/삭제 후 새로고침; B의 A 저장 ID 접근 거부; 중복 PUT 한 행; 외부 제출은 `self_reported_submitted`로만 표시. |
| TC-V1-AUTH-002, TC-V1-COM-004/005, TC-V1-OPP-004 | A/B가 같은 멱등 키·본문을 사용해도 서로의 응답이 노출되지 않음. 동일 사용자의 다른 경로·메서드는 분리. 역할/소속 철회 후 재시도는 저장 응답 재생 전 거부. 같은 revision을 다른 키로 수정해도 한 요청만 성공하며, 동일 키 동시 요청은 한 번만 실행. 실제 실행 증거는 NOT_RUN. |
| TC-V1-AUTH-001/002, TC-V1-COM-001/004 | 미허용 issuer/audience/alg·동적 키 URL·미등록 subject 거부, 이메일 일치만으로 계정/역할 자동 바인딩 불가. 요청에 서버 소유 필드나 알 수 없는 필드를 추가하면 거부. 인증 방식·바인딩 절차 승인 및 실제 구현 전 NOT_RUN. |
| 서버·DB 권한 통합 | 미인증·A·B·관리자 공통 플랫폼 세션 각각으로 FastAPI/chatbot 읽기/쓰기/수정/삭제 허용·거부 확인. MariaDB 런타임 최소 권한 계정으로 스코프 질의 누락·부모 소유권·view/루틴/실시간 우회 경로 검사. 관리 계정으로 PASS 판정 금지. 인증/공통 원장 통합 전 NOT_RUN. |

이 계약의 인증·업무 API·MariaDB 권한 테스트는 **NOT_RUN**이며 해당 기능은 미구현이다. DB 제품 선택은 확정되었지만 클라우드 접속정보가 없어 연결하지 않았다. FastAPI 기반·문서 링크·과거 MVP CI의 성공은 이 업무 계약의 보안 검증이나 최종 프런트 구현 증거가 아니다. 남은 게이트는 OPEN-002의 인증·클라우드 접속/리전/비용, OPEN-003의 가상 권한 시드 책임자·DB 계정 권한, OPEN-009(보존), OPEN-R10(학과 코드), 익명 신고 담당자/작성자 매핑 접근 절차다. 승인 전에는 이 문서가 실제 계정 생성·민감 정책 변경 허가나 공식 학교 정책이 되지 않는다.
