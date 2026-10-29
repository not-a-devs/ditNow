# TASK-L — 취업·진로(careers) 1차 구현

2026-10-30 KST · 브랜치 `feat/careers-programs-firstpass-20261030` · 기준 main `8bb0e7f` · 상태: **review (미마운트 부분 구현, 인증/DB 대기)**

이 문서는 careers 기능 패키지와 신규 웹 feature 모듈의 실제 구현·검증 범위만 기록한다. 전역 API router·factory·인증·DB 모델/마이그레이션·pyproject/uv.lock·package·App·NAV·README·workflow는 수정하지 않았다. 92개 진행표(`06_FEATURE_IMPLEMENTATION_STATUS.csv`)와 보드는 root 소유이므로 아래 §8의 갱신 제안만 남긴다. 어떤 FR도 VERIFIED로 주장하지 않는다.

## 1. 근거와 추적

| 구분 | ID | 근거 |
|---|---|---|
| FR | FR-JOB-001~004, FR-OPP-005, FR-OPP-006 | `docs/v1-draft/09_FEATURE_TRACEABILITY.csv` 30·31·80~83행, `docs/v1-draft/02_FRD.md` §FR-OPP/JOB(공개 채용은 기회 원본 재사용, 이력서·동의·기업 의뢰는 별도 보호 원장) |
| API | API-JOB `/careers/**` (root mount 시 `/api/v1/careers/**`) | `docs/v1-draft/05_DB_API.md` API-JOB |
| RBAC | RBAC-JOB: 본인·취업 담당·동의받은 기업 담당; 동의 없는 이력서/상담 열람 금지 | `docs/v1-draft/04_RBAC.md` |
| DB 후보 | opportunities(재사용), career_profiles, program_applications, employer_requests, 멱등 claim | `docs/v1-draft/05_DB_API.md` — 이 작업은 테이블을 만들지 않음 |
| 정책 | OPEN-R09~R13(접수 형태·취업 동의), DEC-013/DFLT-006(자체 기록), DEC-016/019(MariaDB, 접속 금지) | `docs/v1-draft/11_OPEN_POLICIES_ASSUMPTIONS.md`, `docs/11_DECISION_LOG.md` |
| NFR | NFR-SEC-001/002/003/005/007, NFR-PRIV-002/003, NFR-DATA-003, NFR-REL-001, NFR-UX-001 | `docs/v1-draft/03_NFR.md` |
| TC | TC-V1-JOB-001~004, TC-V1-OPP-005, TC-V1-OPP-006, TC-V1-X03(공모전 팀 모집 연결 부분) | `docs/v1-draft/08_TEST_QA.md`, 추적표 |

## 2. 변경 파일 (모두 소유 범위)

- `services/api/app/features/careers/`
  - `domain.py` — `CareersActor`(서버 검증 신원), `CareerGrant`(UOW에서 읽는 권한), `DemoCareerPolicy`(기본 인스턴스 없음·`basis="DEMO"` 강제), 출처 판정(OFFICIAL_PUBLIC/DEMO/UNKNOWN), https 외부 URL 검사, 연락처·링크·주민번호형 숫자 차단, aware UTC 정규화.
  - `ports.py` — `CareersUnitOfWork`/`CareersTransaction` Protocol과 레코드, 트랜잭션·UNIQUE·CAS·tombstone 계약 문서. **운영 어댑터 없음.**
  - `schemas.py` — 요청 DTO는 `extra="forbid"`(user_id·name·phone·email·file 거부), 응답은 `is_virtual`·`review_status="not_reviewed"`·`publishable=false`·`platform_receives_application=false` 고정 리터럴.
  - `service.py` — 순수 서비스(공개 검색 재사용, 프로필/신청/초안 CRUD, 멱등·CAS·권한 재검사).
  - `linking.py` — community `OpportunityVisibility` Protocol 구현 `ContestTeamLinkVisibility`(FR-OPP-005 seam).
  - `router.py`, `__init__.py` — `create_careers_router(CareersDependencies)`, 기본 `router`는 전부 503. 모든 성공/오류 응답 `Cache-Control: private, no-store`.
- `services/api/tests/test_careers_support.py`(테스트 전용 메모리 fake: 전역 lock `FakeUnitOfWork`, 독립 트랜잭션·한정 잠금 `ScopedLockUnitOfWork`), `test_careers_service.py`, `test_careers_http.py`, `test_careers_concurrency.py`
- `apps/web/src/features/careers/` — `index.tsx`(default `CareersPage`), `PublicPanels.tsx`, `PrivatePanels.tsx`, `ui.tsx`, `api.ts`, `guards.ts`, `types.ts`, `api.test.ts`, `index.test.tsx`
- 이 문서

## 3. 구현된 계약 (상대 경로; root가 `/api/v1` prefix로 mount해야 동작)

| 메서드·경로 | FR | 권한 | 동작·오류 |
|---|---|---|---|
| `GET /careers/jobs?q&department&open_only&limit&cursor` | JOB-001 | 공개 | opportunities `OpportunityCatalog`를 `kind=career`로 재사용(별도 채용 원장 없음). 방어적 재필터, naive 시각 행은 버림, `limit` 1~50 |
| `GET /careers/jobs/{id}` | JOB-001 | 공개 | 비공개·비채용·부재 모두 404 |
| `GET /careers/contests` | OPP-005 | 공개 | 공모전 후보와 `team_link_candidate`, `reference_field="opportunity_id"`. 모집 글 읽기/쓰기 없음 |
| `GET/POST/PATCH/DELETE /careers/me/profile` | JOB-002 | 본인 + `career.profile.self` | 1인 1개 가상 요약(별칭·희망 직무·기술·요약). 없으면 `data.profile=null`. 생성 Idempotency-Key, 수정/삭제 If-Match. 공유(`shared_with`) 항상 빈 목록 |
| `GET /careers/programs` | JOB-003/OPP-006 | 공개(UOW 필요) | `policy_id`·`policy_basis="DEMO"` 표시. DEMO 출처만 `accepts_virtual_application` |
| `POST /careers/programs/{id}/applications` | JOB-003/OPP-006 | 본인 + `career.program.apply.self` | 가상 신청. 공식/UNKNOWN 출처 409, 기간(정책) 409, 중복 활성 신청 409, 정원 409, 1인 활성 한도(정책) 409 |
| `GET /careers/me/program-applications[/{id}]` | 〃 | 〃 | 본인 행만, 타인 행 404 |
| `POST /careers/me/program-applications/{id}/cancel` | 〃 | 〃 | If-Match CAS, 이미 취소 409, 기간 후 취소 여부는 정책 |
| `GET/POST /careers/employer-requests`, `GET/PATCH/DELETE /careers/employer-requests/{id}` | JOB-004 | 본인 + `career.employer_request.draft` | 초안만(`status="draft"`, `publishable=false`). 마감 aware UTC·미래 필수, 1인 초안 한도(정책) |

**권한 순서:** actor 없음 401(UOW 미접촉) → 라우트 의존성이 현재 UOW grant 확인 403(본문·헤더 검증보다 먼저) → 서비스가 쓰기 트랜잭션 안에서 grant 재확인 → 본인 범위 조회(타인=부재=404) → revision/상태 409. 401/403/404 구분은 존재 여부를 흘리지 않는다.

**멱등:** claim 범위 = actor + `POST` + canonical path(UUID 포함) + key, payload SHA-256 저장. 같은 key·같은 본문 → 200 + `Idempotent-Replayed: true`로 현재 상태 반환(취소된 신청은 취소 상태 그대로 — 과거 성공 재표시 없음). 같은 key·다른 본문 409. 삭제 후 claim은 tombstone으로 남아 늦은 재시도 409(부활 없음). replay 전에 현재 grant를 다시 검사하므로 권한 폐기 후 replay는 403. UNIQUE 경합(`StoreConflict`)은 새 트랜잭션으로 1회 재시도해 replay 또는 409.

**원자성:** `with uow.transaction()` 안의 읽기·검사·쓰기·claim 저장이 한 트랜잭션이라는 것은 **Protocol 계약**이다. 테스트 fake는 이를 흉내 낼 뿐 MariaDB InnoDB 격리/잠금을 증명하지 않는다.

**직렬화 계약(리뷰 M1 보완, `ports.py` 모듈 docstring이 기준):**
- 잠금 순서: 한 쓰기 트랜잭션은 actor 잠금 최대 1개 → program 잠금 최대 1개 순서만 쓴다(역순 금지). 프로필 생성/삭제, 신청/취소, 초안 생성/삭제는 claim·한도·count를 읽기 **전에** `lock_actor`를 잡는다. 서비스 순서: grant(빠른 403) → `lock_actor` → grant 재조회(잠금 대기 중 회수 반영) → claim → (신청·취소) `lock_program` → count/상태 → 쓰기. 취소도 같은 순서로 program 잠금을 잡는다.
- `lock_actor`는 1인 활성 신청 한도와 초안 한도를 서로 다른 프로그램/요청 사이에서 직렬화한다. 어떤 행을 잠글지(사용자 행 또는 집계 행)는 DB 소유자가 정한다.
- 가시성: MariaDB 기본 REPEATABLE READ에서 일반 SELECT는 트랜잭션 첫 읽기의 snapshot을 재사용하므로, 잠금 뒤의 grant/claim/count 조회가 옛 snapshot을 보면 정원·한도를 넘을 수 있다. adapter는 해당 트랜잭션을 READ COMMITTED로 실행하거나 잠금 뒤 조회를 locking read(`FOR UPDATE`/`LOCK IN SHARE MODE`, 최신 커밋 버전을 읽음)로 수행해야 한다. 둘 중 무엇을 택할지와 **실서버 격리 수준 설정은 확인하지 않았다**(DB 소유자 결정).
- 오류 변환: UNIQUE/CHECK 위반(예: 1062) → `StoreConflict`, deadlock/lock wait timeout(예: 1213/1205) → `StoreBusy`(adapter가 rollback 후 드라이버 문구 없이 발생). 서비스는 `StoreBusy`를 새 트랜잭션으로 최대 `MAX_TX_ATTEMPTS=3`회까지 재실행하고, 소진하거나 비멱등 쓰기에서 `StoreConflict`가 나면 세부 없는 409를 반환한다(예외 연결·원문 노출 없음, HTTP 테스트로 확인).
- 조건부 UNIQUE: MariaDB에는 partial/filtered index가 없어 "status='applied'일 때만 UNIQUE(user_id, program_id)"를 직접 선언할 수 없다. 예: 생성 열 `IF(status='applied', program_id, NULL)` + UNIQUE(user_id, 그 열)(NULL은 충돌하지 않음). 실제 스키마 선택은 **DB 소유자 과제**로 남긴다.
- 근거(root 제공, 2026-10-30 확인 기록; 이 세션은 네트워크 금지로 직접 재열람하지 않음): [REPEATABLE READ](https://mariadb.com/docs/server/reference/sql-statements/transactions/transactions-repeatable-read), [SELECT … FOR UPDATE](https://mariadb.com/docs/server/reference/sql-statements/data-manipulation/selecting-data/for-update), [Generated Columns](https://mariadb.com/docs/server/reference/sql-statements/data-definition/create/generated-columns).
- 테스트: 기존 전역 lock fake(`FakeUnitOfWork`) 외에 독립 트랜잭션 + actor/program 한정 잠금만 있는 `ScopedLockUnitOfWork`를 추가해 `test_careers_concurrency.py`에서 같은 actor·다른 프로그램 한도, 다른 actor·같은 프로그램 정원, 초안 한도, 잠금 순서, 잠금 대기 중 grant 회수 403, deadlock 재시도·한계·lock timeout 409, 비멱등 UNIQUE 409를 검사한다. **음성 대조**로 actor 잠금을 끄거나 잠금 뒤 snapshot 읽기로 바꾸면 같은 시나리오가 실제로 한도/정원을 넘는 것을 확인해, 통과가 fake의 전역 직렬화 덕분이 아님을 보인다. 이것은 계약 모델 검사이며 **실DB 동시성 검증이 아니다(NOT_RUN)**.

**DemoCareerPolicy:** 기간 강제·기간 후 취소·마감 공모전 연결·1인 활성 신청 수·초안 수는 학교 규정이 아니므로 기본값 없이 root가 명시 주입해야 하고(미주입 503), `basis`가 DEMO가 아니면 생성 실패. 학교 정책 경로는 만들지 않았다.

## 4. BLOCKED / 범위 밖

| 항목 | 사유 |
|---|---|
| 직장/부서 승인, 취업 담당·기업 역할 활성화, 공고 게시·검토 | 운영 역할·권한 미승인(OPEN-R09~R13). 초안 grant는 어떤 역할에도 연결하지 않음 |
| 실제 채용·고용 확인, 외부 기관 제출 | 플랫폼은 접수/확인하지 않음(고정 false 리터럴) |
| 개인 상담 예약·원문(career_appointments) | 민감 본문·동의·보존 정책 미정 — API 미구현 |
| 이력서 파일·실명·연락처, 상담자/기업 공유·동의 | 파일 필드 없음, 연락처 패턴 거부, `shared_with` 항상 빈 목록. 실명은 기계 판별 불가 → UI·문서로 별칭만 허용 명시 |
| 프로그램 실제 심사·선정 | `review_status="not_reviewed"` 고정, 심사 API 없음 |
| 공모전→팀 모집 실제 생성 | community 소유. careers는 seam(`ContestTeamLinkVisibility`)과 후보·ID 참조만 |
| 실 auth·DB adapter·global router mount·OpenAPI 스냅샷·App 라우팅 | root/A 소유. 이 작업에서 DB 접속·컨테이너·migration·GRANT 시도 없음 |
| 삭제된 프로필의 멱등 claim 본문 hash 보존(리뷰 L6) | 별칭·기술처럼 엔트로피가 낮은 본문의 SHA-256은 추측으로 되돌릴 수 있는 파생 정보다. claim TTL, 삭제 후 최소 tombstone(자원 ID·범위만 남기고 hash 삭제 등)·hash 보호 방식은 **정책 미확정**이며 DB 연결(실데이터 저장) 전 차단 조건이다. 이 작업은 임의 보존 기간이나 실개인 자료를 도입하지 않았고 현재 동작(fake에서 claim·hash 유지)을 바꾸지 않았다. DB·개인정보 소유자 결정 필요(NFR-PRIV) |

## 5. 프런트엔드

- `requestData<unknown>('/careers/...')` 후 `guards.ts`가 모든 응답을 런타임 검증한다. 형식 불일치나 서버가 해서는 안 되는 주장(게시 가능, 심사 결과, 공유됨, 비 https 링크, naive 시각)은 `INVALID_RESPONSE`로 표시하지 않는다. 공식 출처 라벨은 https 링크+확인일이 있어야만 표시하고 아니면 "출처 미확인".
- 401은 부모가 모든 개인 패널을 unmount(상태 폐기)하고 로그인 안내, 403은 해당 패널만 제거하고 권한 안내. 공개 검색은 유지. 프로그램 영역은 공개 목록(`ProgramsPanel`)과 개인 하위 컴포넌트(`ProgramApplications`: 내 신청·메모·알림·멱등 key)로 분리해 401/403 시 개인 하위만 unmount한다(리뷰 L4). unmount 뒤 도착한 성공/오류 응답은 버리고 후속 개인 요청도 보내지 않는다(`useAlive`). 안내의 "권한 다시 확인"/"로그인 상태 다시 확인"은 차단만 해제해 패널을 빈 상태로 새로 mount한다(이전 상태 복원 없음).
- guard 문자열 길이는 서버(Python `len`)와 같은 코드 포인트 단위로 센다(리뷰 L5; 이모지 별칭 회귀 테스트). 시각 형식은 끝 고정 `(?:[zZ]|[+-]\d{2}:\d{2})$`만 허용한다(Nit). 이 정규식은 ISO 전체 형식을 강제하지는 않는다(`Date.parse` 가능 여부와 끝 오프셋만 검사).
- 로딩/503/빈/오류/재시도, 실패 시 폼 유지, 같은 입력 재시도는 같은 Idempotency-Key, 입력이 바뀌면 key 회전, 성공은 guard 통과 응답 후에만 표시.
- 텍스트는 React 텍스트 노드로만 렌더링, `dangerouslySetInnerHTML` 없음. 새 인증·가짜 로그인 저장소 없음.
- 전역 App에 mount하지 않았다. 따라서 `npm run build` 번들에는 포함되지 않으며 검증은 **타입 검사 + Vitest/RTL(jsdom)** 뿐이다. 실제 브라우저·390/1280 반응형·DB 연동 완료가 아니다.

## 6. 실제 실행 결과 (2026-10-30, 이 worktree)

### 6.1 독립 리뷰 보완(M1·L1~L6·Nit) 후 재실행

| 명령 | 결과 |
|---|---|
| `services/api`: `uv run --locked pytest` (전체) | **533 passed** (careers 136: service 71·http 53·concurrency 12). 전체 1회 실행 후 동시성 테스트 timeout 조정 뒤 careers 3파일만 1회 재실행(136 passed); 의미 없는 반복 실행은 하지 않음 |
| `uv run --locked ruff check .` / `ruff format --check .` | PASS / PASS (76 files) |
| `uv run --locked python -m app.export_openapi --check` | PASS (careers 미mount라 스냅샷 변화 없음) |
| Python 타입 검사 | NOT_RUN — 프로젝트에 mypy/pyright 설정 없음 |
| `apps/web`: `npm run typecheck` | PASS |
| `npm test` (전체) | **176 passed** (careers 36: api 23·index 13) |
| `npm run build` / `npm run api:types:check` | PASS / PASS |
| `npm ci` / `npm audit` | NOT_RUN — 이번 작업은 네트워크 사용 금지. 의존성·lock 파일 변경 없음 |
| `node scripts/check-agent-config.mjs` / `check-feature-progress.mjs` | PASS (NAV 54 경로, 8 스킬) / errors [] |
| 실 MariaDB 동시성·격리, 실인증, 브라우저(390/1280) | NOT_RUN (DB/네트워크 금지; 라이브 DB는 BLOCKED_TLS) |

이전 기록의 "35회 중 1회 실패"는 상세 로그가 없어 원인을 재현·확인하지 못했다. 이번에는 의미 없는 반복을 하지 않았고 위 1회 실행에서 실패는 없었다. 새 동시성 테스트는 barrier로 두 트랜잭션을 겹치게 한다. 한쪽이 잠금에서 막혀야 하는 경우만 0.3초 뒤 기다림을 포기하고(결과는 잠금이 보장하므로 timing과 무관), 아무도 막히지 않아야 하는 음성 대조는 5초까지 기다린다. 그래도 실패하면 로그를 보존해 원인을 기록해야 한다.

### 6.2 최초 구현 시점 기록

| 명령 | 결과 |
|---|---|
| `services/api`: `uv sync --locked` | PASS (uv = `C:/DIT CSW/ditNow-python-tools/Scripts/uv.exe`, CPython 3.13.3) |
| `uv run --locked ruff check .` / `ruff format --check .` | PASS / PASS (75 files) |
| `uv run --locked pytest` (전체) | **497 passed** (careers 100 포함: service 48·http 52) |
| careers 2파일 반복 실행 | 35회 중 1회 1건 실패(상세 미수집, 장비 부하 중 17초 실행), 이후 33회 연속 PASS. 원인 미확인 — 리뷰 시 재확인 필요 |
| `apps/web`: `npm ci` | PASS, 0 vulnerabilities |
| `npm run api:types:check` / `typecheck` | PASS / PASS |
| `npm test` (전체) | **172 passed** (careers 32: api 21·index 11) |
| `npm run build` | PASS (careers 미mount라 번들 미포함) |
| `npm audit --audit-level=moderate` | 0 vulnerabilities |
| `node scripts/check-agent-config.mjs` | PASS (NAV 54 경로, 8 스킬) |
| `node scripts/check-feature-progress.mjs` | errors [] |
| `git diff --cached --check` (소유 20개 파일 stage 후) | PASS (출력 없음; LF→CRLF 안내만) |

### TC 대응

| TC | 자동 검사(단위/HTTP/RTL, fake) | NOT_RUN |
|---|---|---|
| TC-V1-JOB-001 | 공개 채용만·비채용/비공개 404·출처 3분류·URL 제거·UTC·limit | 실 카탈로그 DB, 브라우저 |
| TC-V1-JOB-002 | 본인 범위·타 계정 null/404·연락처/파일/신원 필드 거부·CAS·삭제 tombstone·권한 폐기 replay 403·동시 같은 key 1건 | 실DB 2계정 영속성 |
| TC-V1-JOB-003 / TC-V1-OPP-006 | 가상 신청·공식 출처 거부·기간/정원/중복/한도·동시 10명 정원 1 초과 없음·취소 CAS·replay 현재 상태 | 실DB 잠금, 실제 심사(BLOCKED) |
| TC-V1-JOB-004 | grant 없는 학생 403(본문 검증 전)·타 초안 404·naive/과거 마감 400·한도·tombstone | 기업 역할·게시(BLOCKED) |
| TC-V1-OPP-005, TC-V1-X03 일부 | 후보 목록과 seam 결과 일치·마감/비공개/비공모전/잘못된 ID false | community와 실제 결합 HTTP, 브라우저 |
| 공통 | 기본 router 17개 경로 503+private, 전역 앱 미mount, 401 시 UOW 미접촉, 500 비밀 미노출, If-Match 형식 | auth/DB 통합, E2E |

## 7. 남은 위험

- 실명은 탐지 불가. 연락처 차단은 정규식 기반이라 우회 가능하다(별칭·기술만 수집하는 최소화가 1차 방어). 리뷰 L3 보완으로 기술명 `ASP.NET`·`ADO.NET`·`VB.NET` 토큰과 연·월(·일) 기간 표기(예: `2023.03-2024.02`)만 예외로 허용했고, 다른 `이름.net`·URL·이메일·전화/주민번호형 숫자열은 계속 거부한다(정상·차단 회귀 테스트). 정규식이 모든 개인정보를 막는다고 보장하지 않는다.
- 리뷰 L1/L2: 공개 검색 `open_only=true`와 공모전 연결 seam은 naive 시각 행/시계를 먼저 걸러 해당 행만 제외하거나 `False`로 거부한다(500 없음).
- 공개 프로그램 목록도 UOW가 필요해 미설정 시 503이다. 공개 프로그램 카탈로그를 별도 읽기 포트로 분리할지는 DB 소유자와 결정.
- `ContestTeamLinkVisibility`를 community에 주입하는 배선은 root 통합 작업이다.
- 응답 `Cache-Control`은 공개 검색에도 `private, no-store`(보수적 기본값).

## 8. root 진행표 갱신 제안 (직접 수정하지 않음)

### 독립 리뷰 후 늦은 권한 오류 보완

root는 이전 개인 패널이 사라진 뒤 도착한 401/403이 새 패널까지 차단하는 재현을 수정했다. 각 읽기 요청은 화면 생존 여부와 요청 세대를 함께 검사하고, StrictMode의 재설정 뒤에도 과거 세대를 폐기한다. 현재 요청의 403은 계속 상위 권한 처리로 전달한다. 새 회귀4개와 기존 careers 합계40개·타입·빌드 PASS, Codex F가 수정 diff와 회귀4개를 읽기 전용으로 독립 재검증해 잔여 차단 finding 없음. 최종 Push 후 CI는 해당 새 HEAD에서 별도로 확인한다. 인증 정책·서버·DB 코드는 변경하지 않았다.

FR-JOB-001~004·FR-OPP-005·FR-OPP-006: main 기준 `NOT_IMPLEMENTED` 유지가 맞고, 병합 시 `PARTIAL`(frontend=미mount 모듈, fastapi=미mount router, mariadb=NOT_RUN, tests=단위/HTTP/RTL PASS), work_branch=`feat/careers-programs-firstpass-20261030`, work_scope는 위 §3·§4. 실제 기능 VERIFIED는 공통 인증·MariaDB adapter·2계정 통합·브라우저 검증 이후.

다음 실행 가능 태스크: root의 공통 auth/UOW adapter 승인 후 `create_careers_router` mount 및 `ContestTeamLinkVisibility`를 community에 주입하는 통합 PR, MariaDB 테이블 제안(career_profiles·program_applications·employer_requests·idempotency claims)을 A 소유자에게 전달.
