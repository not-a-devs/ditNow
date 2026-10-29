# DIT NOW P0 서버·DB·RLS 계약 초안

> TASK-04 · 2026-10-29 · 상태: **설계 기본값 / 승인 대기**. 이 문서는 API·DB·RLS의 구현 입력을 구체화한다. 실제 서버, DB, 정책, 마이그레이션 또는 학교 연동을 구현·승인한 기록이 아니다.

## 1. 범위와 우선순위

기존 92개 [기능 추적표](09_FEATURE_TRACEABILITY.csv) 가운데 P0인 FR-AUTH-001/002, FR-COM-001/004, FR-OPP-004를 먼저 연결한다. FR-COM-005(지원·승인)는 P1이지만 P0 모집 원장의 FK와 정원 제약을 미리 정한다. 공고 원본 FR-OPP-001~003은 P1이며 P0 개인 준비를 시연하려면 관리자 승인 **가상 공고 시드**가 선행된다. 학과·학년 관계는 FR-DEPT-001~008과 공지 대상 권한의 공통 입력이다. 이 문서는 기존 [DB·API](05_DB_API.md), [RBAC](04_RBAC.md), [아키텍처](06_ARCHITECTURE.md), [미확정 정책](11_OPEN_POLICIES_ASSUMPTIONS.md)의 세부 계약이며 DEC-001~014를 변경하지 않는다.

현재 `mvp/src/shared/data/`는 브라우저 localStorage/sessionStorage 모의 구현이다. 이 문서의 서버 권한·DB 불변식·다중 계정 격리는 **미구현**이다. 기존 UI 타입은 전환 참고 자료일 뿐 신뢰 가능한 인증 원장이 아니다.

## 2. 착수 게이트와 기술·비용 확인

| 항목 | 확인 결과와 처리 |
|---|---|
| 기술 기본값 | DEC 문서의 DFLT-001은 React/Vite/TS + Supabase Auth/Postgres/RLS + Vercel **제안**이다. OPEN-002의 공급자·지역·계정·과금 결정은 아직 승인되지 않았다. 아래 `/api/v1`은 공급자와 무관한 논리 계약이다. |
| 공개 가격·보안 사실 | [Supabase 요금표](https://supabase.com/pricing)는 확인일 2026-10-29 기준 Free $0, DB 500 MB, Auth MAU 50,000, 비활성 1주 후 일시 중지를 표시한다. 무료 한도와 서비스 조건은 변경될 수 있으므로 실제 프로젝트 개설 직전에 재확인한다. [공식 RLS 문서](https://supabase.com/docs/guides/database/postgres/row-level-security)는 노출 스키마의 테이블마다 RLS와 GRANT를 함께 설정하고, `service_role` 비밀키를 브라우저에 두지 않도록 요구한다. |
| 프로젝트 권한·비용 | 팀 소유 계정, 프로젝트 생성 권한, 리전, 청구 방식, 무료 한도 초과 정책, 비밀키 보관 담당자, 배포 권한은 **미확인**. 새 서비스 개설·유료 플랜·실제 데이터 입력은 하지 않는다. |
| 인증 결정 | 가상 시연 계정의 관리 책임자 OPEN-003이 미결정이다. 공개 회원가입은 기본 거부하고 승인된 가상 계정 시드만 허용하는 설계 후보로 둔다. 학교 SSO·운영 DB·실제 학생 확인은 범위 밖이다. |
| 착수 상태 | 이 계약의 문서 검토는 가능하다. 실제 Auth/DB/RLS 구축은 OPEN-002/003, 비밀키 소유자, 테스트용 프로젝트와 비용 한도를 승인한 뒤 별도 PR에서 진행한다. |

## 3. 공통 API 형식

- HTTPS `/api/v1`; 인증 필요 요청의 주체는 검증된 세션/JWT에서 서버가 도출한다. 본문·쿼리의 `user_id`, `role`, `department_id`, `academic_year`를 권한의 증거로 사용하지 않는다.
- 성공: `{ data, resource_version, server_time }`; 목록은 `{ data, next_cursor, server_time }`. 실패: `{ code, message, field_errors?, retryable, request_id }`. `server_time`은 UTC ISO 8601, 식별자는 UUID. 공개 문자열 입력은 정규화·길이 제한·출력 이스케이프를 적용한다.
- 400 필드 검증, 401 세션 부재/만료, 403 승인 범위 밖, 404 없는 자원, 409 중복·버전·상태 경합, 429 요청 제한, 5xx 장애. 비공개 자원은 타인 소유와 부재를 구별할 수 없도록 외부에는 404로 정규화하고 내부 감사에는 사유 코드를 남긴다.
- 변경 요청은 `If-Match: <resource_version>` 또는 멱등 키를 받는다. 서버는 중복 키와 요청 본문 해시를 연결하고 동일 요청 재시도에는 같은 결과를 돌려준다. 동일 키에 다른 본문은 409. 페이지네이션은 불투명 cursor와 제한된 `limit`을 사용한다.
- 파일·외부 URL·공지 공식성은 별도 원장/권한의 결과다. 시연 레코드에는 `source_kind=DEMO|USER_DEMO`를 반환하고 실제 제출·학교 확인 상태처럼 표시하지 않는다.

## 4. P0 원장과 무결성

아래는 논리 스키마다. 물리 타입·인덱스·migration 문법은 승인된 공급자에서 별도 리뷰한다. `id uuid PK`, `created_at/updated_at timestamptz UTC`, 변경 가능한 행의 `revision integer > 0`을 공통으로 사용한다. FK 삭제는 기본 제한, 공개 콘텐츠 삭제는 상태 전이와 감사 기록으로 처리한다. `auth.users` 참조는 Supabase 채택 시에만 적용한다.

| 테이블 | 필수 필드와 FK/유일성 | 소유·상태 불변식 |
|---|---|---|
| `profiles` | `user_id PK`, `display_name`, `status`, `source_kind` | 인증 ID와 1:1. 가상 프로필만 P0. 이메일·로그인 비밀은 별도 인증 원장; 공개 모집 응답에 이메일 없음. |
| `departments` | `id`, `code UNIQUE`, `name`, `source_url?`, `checked_at?` | 공개 확인 자료와 가상 시드 구분. 코드 미확정이면 운영 공식 코드로 가장하지 않음(OPEN-R10). |
| `academic_memberships` **신규 제안** | `id`, `user_id FK`, `department_id FK`, `academic_year > 0?`, `term_id?`, `status`, `valid_from`, `valid_to?` | 승인된 현재 소속 한 건을 권위로 사용. 휴학·전과·기간 만료 시 권한 재평가. 학년 상한·학제는 미확정이며 시연 속성일 뿐 실제 학적 아님. P0에서 `profiles.department_id/year`는 읽기 projection일 뿐 권한 원장 아님. |
| `role_assignments` | `id`, `user_id FK`, `role`, `scope_type`, `scope_id?`, `status`, `valid_from/to` | `(user_id,role,scope_type,scope_id,유효 기간)` 중복 금지. 관리자 승인 트랜잭션만 변경; 일반 사용자의 직접 INSERT/UPDATE/DELETE 금지. |
| `anonymous_posts_private` | `id`, `author_id FK`, `title`, `body`, `status`, `revision` | 작성자 매핑은 비공개. `active→hidden/deleted`, 복구는 신고 정책 승인 이후. 작성자만 자기 글 수정/삭제, 운영자 조치는 감사 필수. |
| `anonymous_posts_public` | `id FK`, `title`, `body`, `status`, `created_at/updated_at`, `comment_count` | **별도 공개 읽기 모델**. `author_id`, 이메일, 학과, 학년, 작성자와 연결 가능한 안정 식별자를 두지 않는다. 비공개 원장과 동일 트랜잭션에서 갱신. 공개 조회에서 private 테이블에 join하지 않는다. |
| `recruitments` | `id`, `owner_id FK`, `opportunity_id FK?`, `title`, `body`, `field`, `roles`, `capacity`, `deadline_at`, `status`, `revision` | 실명 활동 프로필만 노출. `capacity ≥ 1`은 **모집자 포함 총 인원**. `open→closed/cancelled`; 서버 시각으로 마감 판정. 외부 공고 연결은 원본 ID만 사용. |
| `recruitment_applications` | `id`, `recruitment_id FK`, `applicant_id FK`, `message`, `status`, `created_at` | `(recruitment_id,applicant_id)` 유효 지원 중복 금지. 모집자 자기 지원 금지. `pending→accepted/rejected/withdrawn`; 승인 시 행 잠금/트랜잭션으로 `1 + accepted_count ≤ capacity` 보장. P1 UI 전에도 스키마 제약 정의. |
| `opportunities` | `id`, `kind`, `title`, `organization`, `eligibility`, `target_scope`, `deadline_at`, `submission_mode`, `destination?`, `original_url?`, `source_kind`, `source_url?`, `checked_at?`, `status` | P0는 관리자 승인 가상 시드만 읽음. `external_document_submission|external_link|info_only` 구분; 원문 없는 시연 공고는 DEMO 표시. |
| `saved_opportunities` | `id`, `user_id FK`, `opportunity_id FK`, `status`, `memo`, `self_reported_submitted_at?`, `revision` | `(user_id,opportunity_id) UNIQUE`. `interested→preparing→self_reported_submitted/closed` 기본 흐름. 실수 정정은 본인 요청과 감사 기록으로 허용하되 외부 접수 확인으로 승격 불가. |
| `opportunity_check_items` | `id`, `saved_id FK`, `text`, `sort_order`, `completed_at?`, `revision` | 부모 저장 항목의 본인만 CRUD. 항목 순서/완료를 서버가 원자적으로 갱신. |

`academic_memberships` 추가는 기존 `profiles`·`role_assignments`·`enrollments`의 의미를 바꾸지 않기 위한 제안이다. 실제 테이블명·학기 모델은 승인 전 변경 가능하다. 익명 공개 모델은 일반 SQL view가 소유자 권한으로 RLS를 우회할 수 있다는 [공식 설명](https://supabase.com/docs/guides/database/postgres/row-level-security)을 고려해 별도 테이블을 기본값으로 둔다. 공개 모델 동기화 실패 시 비공개 원장 commit도 실패해야 한다.

소속 상태 후보는 `pending|active|inactive`; 권한은 `active`이고 유효 기간 안인 기록만 인정한다. `role_assignments.scope_type` 후보는 `platform|department|course_offering`이며 역할은 기존 학생·교수·조교·관리자 유형을 사용한다. 한 사용자에게 유효한 주 소속이 겹치지 않도록 DB 제약 또는 직렬화 트랜잭션으로 막는다. 학과 코드/학년별 기간·교직원 다중 소속·학기 변경 규칙은 학교 정책으로 확정하지 않고 OPEN-003/OPEN-R10에 남긴다.

## 5. 동작별 API 계약

모든 본문/응답은 설계 후보이며 기존 mock API의 호출 방식과 자동으로 호환된다는 뜻이 아니다. 응답은 위 공통 래퍼를 생략해 표시한다.

| 계약·FR/TC | 메서드/경로 | 요청 → 응답·저장 | 권한·주요 실패 |
|---|---|---|---|
| API-ID · FR-AUTH-001 · TC-V1-AUTH-001 | `GET /session`, `POST /session/logout` | 인증 토큰 → 본인 `user_id`, 승인 역할·현재 소속·`source_kind`; 로그아웃은 세션 종료 결과 | 401 만료. 인증 발급/갱신 방식은 공급자 선택 후 명세; 클라이언트 전송 ID로 세션 생성 금지. |
| API-ID · FR-AUTH-002 · TC-V1-AUTH-002 | `GET /me/affiliation`, `POST /admin/demo-affiliations`, `PATCH /admin/demo-affiliations/{id}` | 관리자 입력: 가상 대상 ID·학과·학년·역할·유효 기간·사유 → 승인된 소속/역할 revision | 승인 관리자만 변경, 본인 승격 403, 잘못된 FK 400, 중복/겹침 409; 감사 기록. OPEN-003 승인 전 관리자 쓰기 API 배포 금지. |
| API-COM · FR-COM-001 · TC-V1-COM-001 | `GET /anonymous-posts`, `GET /anonymous-posts/{id}`, `POST /anonymous-posts`, `PATCH /anonymous-posts/{id}`, `DELETE /anonymous-posts/{id}` | 제목·본문 → 공개 글(작성자 식별 필드 없음), 본인 여부는 `is_mine` boolean으로만 계산; create/update/delete와 공개 모델 원자 갱신 | 승인된 가상 학생; 자기 글만 변경. 타인 수정 404, 버전 충돌 409, 비활성 글 공개 조회 404. |
| API-COM · FR-COM-004 · TC-V1-COM-004 | `GET /recruitments`, `GET /recruitments/{id}`, `POST /recruitments`, `PATCH /recruitments/{id}`, `POST /recruitments/{id}/close` | 제목·본문·분야·모집 역할·총 정원·마감·선택 공고 ID → 실명 활동 프로필/상태/revision | 승인된 가상 학생; 모집자만 변경. 정원 미만 400, 타인 변경 404, 마감/취소 경합 409. 학생 이메일은 응답 제외. |
| API-COM · FR-COM-005 · TC-V1-COM-005 | `POST /recruitments/{id}/applications`, `POST /recruitments/{id}/applications/{id}/decision`, `POST /recruitments/{id}/applications/{id}/withdraw` | 지원 메시지 → 지원 상태; 결정 `accept|reject` → 팀 인원/상태 | **P1, P0 공개 UI 범위 밖**. 본인 지원/철회, 모집자 승인; 중복·마감·정원 초과 409. 멱등 키와 행 잠금 필수. |
| API-OPP · FR-OPP-004 · TC-V1-OPP-004 | `GET /me/saved-opportunities`, `PUT /me/saved-opportunities/{opportunity_id}`, `PATCH /me/saved-opportunities/{opportunity_id}`, `DELETE /me/saved-opportunities/{opportunity_id}` | 공고 ID, 준비 상태·메모 → 본인 저장 항목/revision; PUT 반복은 동일 레코드 반환 | 현재 세션 본인만. 없는/비공개 공고 404, 버전 경합 409. 삭제는 본인 체크 항목과 함께 처리; 감사/보존 정책은 OPEN-009. |
| API-OPP · FR-OPP-004 · TC-V1-OPP-004 | `POST /me/saved-opportunities/{opportunity_id}/checks`, `PATCH /me/saved-opportunities/{opportunity_id}/checks/{id}`, `DELETE /me/saved-opportunities/{opportunity_id}/checks/{id}` | 체크 문구·순서·완료 여부 → 갱신된 항목/revision | 항목의 부모 소유권까지 확인. 타 계정 항목 404, 중복 요청 멱등, 정렬 충돌 409. |

`POST /session/login`의 실제 자격 증명·토큰 교환은 Auth 공급자 채택 시 그 공급자 계약으로 정의한다. 기존 시연용 이메일/비밀번호를 운영 인증으로 이관하지 않는다. 실명 모집 프로필은 `profiles`의 허용된 필드만 반환한다. 익명 글과 실명 모집 사이에 공개 작성자 연결 API는 없다.

## 6. RLS·GRANT와 서버 권한 매트릭스

기본 거부. 공급자 선택 시 **노출 테이블마다 RLS 활성화 + 역할별 최소 GRANT + SELECT/INSERT/UPDATE/DELETE별 정책 + 양성/음성 테스트**를 같은 변경으로 제출한다. 정책 조건은 매 요청 현재 DB 소속/역할/자원 상태를 조회하며 오래된 JWT의 학과·학년 claim만 사용하지 않는다. 서버가 비밀키로 RLS를 우회한다면 동일 검사를 서버 트랜잭션에서 수행하고 증명해야 한다. 비밀키는 브라우저·저장소·로그에 없음.

| 자원 | 공개/미인증 | 승인 학생 | 모집자·작성자 | 관리자/운영자 |
|---|---|---|---|---|
| `profiles`, `academic_memberships`, `role_assignments` | 없음 | 본인 최소 projection 조회; 직접 역할·소속 쓰기 불가 | 동일 | 승인 범위의 변경만 서버 전용 절차 + 감사. OPEN-003 전 쓰기 비활성 |
| `anonymous_posts_private` | 없음 | **테이블 직접 접근 불가** | 서버 전용 작성/수정/삭제 경로에서 소유권 확인 | 별도 신고 승인 경로만; 일반 관리자 전체 신원 조회 금지 |
| `anonymous_posts_public` | 없음 | 활성 글만 SELECT, 직접 쓰기 불가 | `is_mine`은 서버에서 계산 | 운영 조치는 비공개 원장에 기록 후 공개 모델 갱신 |
| `recruitments` | 없음 | 공개 모집 SELECT/본인 INSERT | 본인 UPDATE/종료 | 허가된 조치만 감사 기록 |
| `recruitment_applications` | 없음 | 본인 지원/철회/조회 | 본인 모집의 지원 조회·결정 | 일반 관리자 기본 거부 |
| `opportunities` | 출처가 허용한 공개 정보만 별도 공개 projection | 공개/대상 공고 SELECT | 동일 | 승인 담당자만 공고 쓰기(P1) |
| `saved_opportunities`, `opportunity_check_items` | 없음 | `auth.uid() = user_id` 또는 부모 소유로 CRUD | 동일 | 일반 관리자 기본 거부; 복구는 별도 승인 절차 |

RLS 정책이 테이블 행을 막아도 **컬럼 노출·view 소유권·함수 실행권**은 별도 검토한다. 익명 private/public 간 join, `author_id`를 담은 Realtime payload, 역할 변경을 허용하는 넓은 `UPDATE`, `service_role` 클라이언트 노출은 차단 이슈다. 익명 댓글은 FR-COM-002의 P2이므로 이 계약에서 별도 공개 원장/별칭을 구현 완료로 간주하지 않는다.

## 7. 상태 전이·이벤트·동시성

1. 승인된 가상 소속/역할 변경은 한 트랜잭션에서 기존 유효 기간 종료→신규 기록→감사 기록. 변경 후 API·채팅·공지·파일 조회가 새 DB 소속을 사용하도록 재검증한다. 열린 실시간 연결은 권한 변경 이벤트 또는 재인증으로 끊고, 실패 시 짧은 재검증 주기를 둔다.
2. 익명 작성/수정/삭제는 private 행과 public 읽기 모델을 원자적으로 갱신한다. 삭제한 글의 공개 검색/캐시도 제거한다. 공개 응답·로그·오류·분석에 작성자 ID를 내보내지 않는다.
3. 모집 지원 승인에는 모집 행 잠금→마감/상태 재검사→승인 인원 계산→지원 상태 갱신→팀 멤버 반영 순서를 사용한다. 두 동시 승인이 마지막 한 자리를 넘지 못한다. 지원 이벤트/알림은 commit 후 outbox로 발행한다.
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
| TC-V1-COM-001, TC-V1-X02 | A 익명 글 생성/수정/삭제 후 B 조회; B·미인증자의 타인 변경 거부; 공개 JSON·검색·실시간·로그에 `author_id`/이메일/소속이 없음. 새로고침·재로그인에도 원장 일치. |
| TC-V1-COM-004/005 | A 실명 모집과 공고 원본 연결; B 지원, A 승인, C 동시 승인에서 총 정원 초과 없음. A 프로필은 허용 필드만 노출하고 익명 글과 연결되지 않음. P1 지원 UI 미구현이면 해당 테스트 NOT_RUN. |
| TC-V1-OPP-004, TC-V1-X03 | A 공고 저장·상태·체크 수정/삭제 후 새로고침; B의 A 저장 ID 접근 거부; 중복 PUT 한 행; 외부 제출은 `self_reported_submitted`로만 표시. |
| RLS 통합 | 미인증·A·B·관리자 토큰 각각으로 모든 노출 테이블 SELECT/INSERT/UPDATE/DELETE 허용/거부 확인. `service_role` 없이 테스트, view/RPC/Realtime 우회 경로 포함. |

현재 테스트 실행 상태는 **NOT_RUN**: 서버·DB·RLS 자체가 없다. 문서 링크 검사·MVP CI는 설계 정합성만 확인한다. 필수 결정은 OPEN-002(공급자/리전/비용), OPEN-003(가상 권한 시드 책임자), OPEN-009(보존), OPEN-R10(학과 코드), 익명 신고 담당자/작성자 매핑 접근 절차다. 승인 전에는 이 문서가 구현 허가나 공식 학교 정책이 되지 않는다.
