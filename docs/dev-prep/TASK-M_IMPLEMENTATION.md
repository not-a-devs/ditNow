# TASK-M — 학사·출결 1차 구현 (academics)

상태: **PARTIAL / TESTED**(공급자 독립 코드·테스트 fake 범위). 공통 인증·MariaDB·실제 학적/수강/분반 원장·전역 router/셸 연결은 **BLOCKED / NOT_RUN**이다. 어떤 FR도 운영 VERIFIED로 표시하지 않는다.

브랜치 `feat/academics-attendance-firstpass-20261030`, worktree `C:/DIT CSW/ditNow-academics`. 2026-10-30 작성.

## 선행 기준과 소유 범위

관련 요구사항: [FRD](../02_FRD.md) FR-ATT-001~002, [통합 FRD](../v1-draft/02_FRD.md) FR-ACA-003~009 분해 규칙, [추적표](../v1-draft/09_FEATURE_TRACEABILITY.csv) 해당 행, RBAC-ACA/RBAC-ATT([RBAC](../v1-draft/04_RBAC.md)), API-ACA/API-ATT·academic_requests/grades/attendance_* ([DB/API](../v1-draft/05_DB_API.md)), NFR-SEC-001/002/003/007, NFR-ID-002, NFR-PRIV-001/004, NFR-REL-001/003/004, NFR-DATA-003, NFR-UX-001, TC-V1-ACA-003~009, TC-V1-ATT-001~002, TC-V1-X07/X09([QA](../v1-draft/08_TEST_QA.md)). OPEN-R01~R03([미결정](../v1-draft/11_OPEN_POLICIES_ASSUMPTIONS.md))은 해소하지 않았다.

수정 파일(이 태스크 소유만):
- `services/api/app/features/academics/`: `models.py`(입출력·출처), `policy.py`(DemoAcademicPolicy), `idempotency.py`, `ports.py`(repository/UOW Protocol), `service.py`, `router.py`
- `services/api/tests/test_academics_support.py`(테스트 전용 fake), `test_academics_service.py`, `test_academics_http.py`
- `apps/web/src/features/academics/`: `index.tsx`(default), `CoursesPanel.tsx`, `RequestsPanel.tsx`, `AttendancePanel.tsx`, `shared.tsx`, `api.ts`, `models.ts`, `academics.module.css`, `api.test.ts`, `index.test.tsx`
- 이 문서

공통 API router/factory/auth/DB models/migrations/pyproject/uv.lock/package/App/NAV/README/workflow/진행표 CSV/`mvp/`는 수정·복사하지 않았다. 진행표(06)·보드(05) 갱신은 ORCH 소유라 이 PR에 포함하지 않는다.

## 실제 구현과 남은 범위

| FR | 1차 코드 | 남은 범위/차단 |
| --- | --- | --- |
| FR-ACA-003 | 가상 개설강좌 검색(학기·검색어·limit≤100)·상세·강의계획 요약. 출처 `DEMO`/`OFFICIAL_PUBLIC`(https URL+확인일 필수)/`UNKNOWN` 구분 | 실제 강의계획 원문 스냅샷·전공 필터·페이지 커서 미구현 |
| FR-ACA-004 | 본인 시연 수강신청(멱등)·취소(CAS)·정원 잠금·시간 충돌·주입 학점 한도·UTC 반열림 기간·현재 등록 자격 | 실제 수강 규정·대기열·교무 처리·시간표 연동 BLOCKED |
| FR-ACA-005 | 본인 가상 성적 목록·표시 학점 단순 합. `graduation_judgement=NOT_PROVIDED`, `official_effect=NONE` | 공식 이수 판정·졸업 요건 버전·교무 조회 BLOCKED |
| FR-ACA-006~008 | 휴학·복학·재입학·전과 가상 요청 draft(멱등)/수정(CAS)/submit(기간)/withdraw(tombstone) | 상담·서명·여석·승인·학적 반영·권한 재계산 BLOCKED |
| FR-ACA-009 | 본인 시연 성적 대상 성적 정정 요청 동일 흐름 | 성적포기·성적 변경 권위·교무 심사 BLOCKED |
| FR-ATT-001 | 교수: 시연 세션 시작(멱등, 서버 6자리 코드)/종료(CAS)/명단별 기록·최종 표시 수정(사유 필수·변경 이력)/정정 처리. 학생: `DEMO_CODE` 체크인(시도 횟수 제한) | 블루투스·캠퍼스락·QR·위치·LMS 온라인 출석 BLOCKED; 지각/결석 판정 규칙 없음 |
| FR-ATT-002 | 학생 본인 세션·기록·정정 요청(멱등)·처리 상태 조회 | 공식 출결 반영·이의 절차 BLOCKED |

차단 플로우는 API에 존재하지 않거나 503/400이다: 운영 승인, 공식 성적 변경, 졸업 판정, 증명서, 등록금/금융, 블루투스 신원 확인(`method`는 `DEMO_CODE`만 허용). 첨부 파일·민감 서류 필드는 `extra=forbid`로 400이다.

## 권한·데이터 경계

- 신뢰 actor는 서버 주입 `get_academics_actor`만 사용하고 기본값은 503이다. `get_academics_service` 기본값도 503이며 메모리 fake는 `tests/`에만 있다. router는 전역 앱에 mount하지 않았다(테스트로 404·OpenAPI 미노출 확인).
- 학생 흐름은 매 UOW의 `standing()`(현재 ledger 자격)을 다시 읽고, 출결은 `attendance_grant(offering_id)`(현재 수강/담당)를 다시 읽는다. 클라이언트 role/student_id/status 필드는 400이다.
- 인가 선행 후 조회: 타인 수강·요청·성적·출결 기록·정정은 존재하지 않는 자원과 같은 404다. 분반 grant 없음 404, 비활성/역할 불일치 403.
- 응답에서 `student_id`/`actor_id`/`failed_attempts`를 제거한다. 체크인 코드는 담당 교수 응답에만 있다. 학생 정정 목록에 다른 학생 정보가 없다.
- 모든 정상·오류·검증·미설치·예외 응답은 `Cache-Control: private, no-store`. 예외 내용은 응답/로그에 남기지 않는다. 409/429/400 규칙은 `field_errors.rule`(예: `CAPACITY_FULL`, `TIME_CONFLICT`, `CREDIT_LIMIT`, `WINDOW_CLOSED`, `STALE_REVISION`, `CODE_MISMATCH`, `ATTEMPT_LIMIT`)로 고정 코드만 준다.
- 학기/분반 ID는 기존 campus 학기·classroom 분반 원본 ID 참조다. 이 모듈은 학기·분반 권위 원장을 만들지 않는다.

## 시연 정책과 학교 정책 분리

`DemoAcademicPolicy`는 label에 `DEMO`가 있어야 하고, 학점 한도·체크인 창(≤24h)·시도 한도·학기별 수강 기간·요청 종류별 기간을 **배포 시 주입**한다. 코드에 학교 수치 기본값은 없다. 주입 전에는 정책 조회·수강신청/취소·요청 작성/수정/제출/철회·세션/체크인/표시/정정 쓰기가 503이다(카탈로그·본인 조회는 저장소만 필요). 기간은 aware datetime만 허용하고 UTC로 정규화하며 `[opens_at, closes_at)` 반열림이다. 정책 응답은 `policy_source=DEMO`, `school_rules=NOT_CONNECTED`, 차단 목록을 함께 준다.

시연 처리 가정(학교 규정 아님): 같은 학기 활성 수강 중복 금지, 수강 취소도 같은 기간 안, 같은 종류(성적 정정은 같은 성적)의 활성 요청 1건, 분반당 열린 세션 1개, 체크인은 미기록 상태에서만, 교수 최종 표시는 세션 종료 후에도 사유와 함께 수정 가능, 정정 요청은 최종 표시(PRESENT/LATE/ABSENT)에만.

## 멱등·동시성·원자성 계약

- 생성(수강신청·요청·세션·정정)은 `Idempotency-Key`(16~100자 `[A-Za-z0-9-]`) 필수. 클레임은 actor+method+canonical path+key 네임스페이스와 검증된 body의 정규 JSON SHA-256을 저장한다. 같은 hash 재시도는 원래 행의 현재 상태를, 다른 hash는 409를 준다. 다른 actor의 같은 key는 별개 네임스페이스다.
- 재시도에서도 현재 자격/grant를 먼저 재검증한다(권한 폐기 후 replay 403 테스트).
- 삭제 대신 tombstone: 수강 `DROPPED`, 요청 `WITHDRAWN`(사유 텍스트는 최소화로 null). 원 클레임 replay는 tombstone을 돌려주며 부활하지 않는다.
- 상태 변경은 `expected_revision` CAS이고 불일치 409 `STALE_REVISION`. 출결 기록은 revision 0이 "아직 없음"이다.
- **원자성은 실 DB 보장이 아니다.** `ports.py`가 어댑터 계약(같은 트랜잭션의 자격 재조회, `lock_seats` 행 잠금, 클레임+행 동시 저장, 예외 시 전체 rollback, ENROLLED 유일성)을 명시한다. 테스트 fake는 전역 잠금으로 직렬화하고 예외 시 snapshot으로 되돌릴 뿐이다. 체크인 코드 불일치는 시도 횟수를 commit한 뒤 400을 던진다.

## 프런트엔드

`apps/web/src/features/academics/index.tsx` default React TS 컴포넌트(자체 CSS module). 전역 App/라우터에 mount하지 않았다. 공유 `requestData<T>('/academics/...')`만 사용하고 `/api/v1`을 붙이지 않는다(실제 `requestData`+fetch stub URL 회귀 테스트). 모든 성공 응답은 런타임 guard를 통과해야 렌더하며 실패 시 성공 문구를 표시하지 않는다. 401/403은 개인 화면 전체를 비우고 상위 오류와 "다시 확인"만 남긴다. 로딩/503/빈/오류/재시도 상태, 실패 후 폼 보존, 같은 입력 재시도 key 재사용·입력 변경 시 key 회전을 구현했다. 공식 출처는 https+확인일이 있는 `OFFICIAL_PUBLIC`만 링크하며 DEMO/UNKNOWN은 링크하지 않는다. 텍스트는 React 이스케이프로만 렌더한다. 새 로그인·가짜 세션 저장소를 만들지 않았다. `ApiError`가 `field_errors`를 전달하지 않으므로 화면은 409 규칙별 사유 대신 공통 충돌 문구를 보인다(후속 공통 lib 소유자 결정).

## 테스트 ID와 실제 결과 (2026-10-30, Windows, Python 3.13/uv, Node 22)

| TC | 자동 검증 내용 | 결과 |
| --- | --- | --- |
| TC-V1-ACA-003 | 학기·검색어·limit 필터, 없는 강좌 404, DEMO/OFFICIAL_PUBLIC/UNKNOWN 출처 검증 | PASS(단위) |
| TC-V1-ACA-004 / X07 | 멱등 replay·payload 충돌·타 actor 분리, 시간 충돌·학점 한도·정원·중복, UTC 반열림 기간, 자격 폐기 후 replay 403, **8명 병렬 정원 2 초과 없음**, 같은 학생 6중 병렬 1건, 취소 CAS·tombstone·좌석 반환 | PASS(fake 직렬화) |
| TC-V1-ACA-005 / X09 | 본인 성적만, 타 학생 성적/ID 미노출, 졸업 판정 미제공·공식 효력 NONE | PASS(단위) |
| TC-V1-ACA-006~009 | 5종 대상 검증, 타인 성적/없는 학과·학기 404, 활성 중복 409, 종류 미주입 503, CAS·제출 기간·철회 tombstone·replay, 타 학생 404, UOW 예외 시 클레임·행 rollback | PASS(단위) |
| TC-V1-ATT-001 | 교수만 세션 시작·종료, 코드 교수만 노출, 체크인 코드 불일치 시도 commit·한도 429, 창/종료 409, BLUETOOTH 400, 교수 표시 CAS·이력(행위자 ID 비노출), 교수 grant 폐기 403, 병렬 표시 1건 | PASS(단위) |
| TC-V1-ATT-002 | 학생 본인 기록만, 타 학생 기록 정정 404, 중복 정정 409, 교수 반영/반려와 이력, 수강 폐기 후 replay·조회 403 | PASS(단위) |
| HTTP | 미설치 actor/service 503+no-store, 정책 미주입 503, 전역 앱 미mount, key 누락/형식 400, 위조 student_id/status/attachment 400, 규칙 코드, 404 동일 응답, 예외 비밀 미노출, OpenAPI 내부 record 비노출 | PASS(TestClient) |
| FE | 11개 경로 단일 `/api/v1` prefix, ID 인코딩, guard 거부, 503/401/403 처리, key 재사용·회전, 폼 보존, 허위 성공 미표시, 정책 배너, 체크인 DEMO_CODE, 교수 전용 코드 | PASS(Vitest/RTL) |

실행 명령과 결과:
- `services/api`: `uv sync --locked` PASS, `uv run --locked ruff check .` PASS, `ruff format --check .` PASS(75 files), `uv run --locked pytest` **437 passed**(academics 신규 40, 기존 회귀 포함; TestClient deprecation 경고 1건 비차단).
- `apps/web`: `npm ci` PASS, `npm run api:types:check` PASS(공개 스냅샷 불변), `npm run typecheck` PASS, `npm test` **171 passed**(academics 신규 31), `npm run build` PASS, `npm audit --audit-level=moderate` 0 vulnerabilities.
- `node scripts/check-agent-config.mjs` PASS, `node scripts/check-feature-progress.mjs` errors [], `git diff --check` PASS.

NOT_RUN: 실제 MariaDB 어댑터·잠금/격리·재조회·새 세션, 공통 인증 actor 브리지, 실제 2계정 로그인, 전역 router/셸 mount 후 E2E, 실브라우저 390/1280 화면, 부하. DB·네트워크 접속은 시도하지 않았다(root/DB 단일 소유자 관할).

## 후속(사람 승인/root 리뷰 대기)

1. A(공통 DB/auth 소유): enrollments/grades/academic_requests/attendance_sessions/attendance_records/attendance_change_logs/attendance_corrections/idempotency claim 테이블·유일성·FK(기존 terms/course_offerings/departments 참조) 설계와 `ports.py` 어댑터. migration·GRANT는 root/DB 소유자만.
2. root 통합: actor/service 브리지 주입, `DemoAcademicPolicy` 승인 값 주입, `/api/v1` router mount·OpenAPI 스냅샷·셸 경로 연결, 진행표 06/보드 05 갱신.
3. 정책 결정(OPEN-R01~R03): 실제 수강·학적·성적·출결 판정 규칙과 승인 권한. 결정 전 운영 활성화 금지.
4. 공통 lib 소유자: `ApiError`에 안전한 규칙 코드 전달 여부.
