# TASK-COMMUNITY — 익명 게시글과 실명 모집 1차 구현 기록

- 작성일: 2026-10-30 (독립 리뷰 결함 수정 2차 반영: 같은 날)
- 브랜치: `feat/community-recruitment-firstpass-20261030` (독립 worktree, `origin/main` 병합 커밋 `f54c14a` 포함 — 리베이스/force 없음)
- 상태: `review` — 기능 패키지·단위/HTTP 계약 테스트·프런트 Vitest 완료. **공통 앱 미연결(라우터 미마운트), DB·인증 미연결, 실제 DB 미실행(NOT_RUN).**
- 근거 문서: `docs/02_FRD.md` §FR-COM-001~005, `docs/03_NFR.md`, `docs/05_DATA_MODEL.md`, `docs/08_TEST_QA.md`, `docs/v1-draft/04_RBAC.md`(RBAC-COM), `docs/v1-draft/09_FEATURE_TRACEABILITY.csv`, `docs/v1-draft/13_P0_SERVER_DB_RLS_CONTRACT.md`(API-COM), `docs/10_AI_RUNBOOK.md`.
- `mvp/` 소스는 읽거나 복사하지 않았다.

## 1. 범위와 추적

| 요구사항 | 우선순위 | 이번 작업 | TC |
| --- | --- | --- | --- |
| FR-COM-001 전교 익명 자유게시판 글 CRUD | P0 | 서비스·DTO·라우터·테스트 구현 | TC-V1-COM-001, TC-002, TC-V1-X02 |
| FR-COM-004 실명 팀/대회/공모전 모집글 CRUD | P0 | 서비스·DTO·라우터(생성/조회/수정/마감)·테스트 구현 | TC-V1-COM-004, TC-003(부분), TC-V1-X02 |
| FR-COM-005 역할/인원/마감, 지원·승인 | P1 | **순수 도메인 규칙만**(정원 계산·상태 전이·지원 사전검사). 지원 API/저장소 없음 | TC-V1-COM-005 → NOT_RUN |
| FR-COM-002/003/006/007 | P2 | 범위 외 | — |

NFR: NFR-SEC-001(보호 API 인증 필수), NFR-SEC-002(서버 소유권 검사), NFR-SEC-005(길이·형식·제어문자 검증, HTML은 텍스트로 처리), NFR-PRIV-001(익명 공개 응답 식별자 제외), NFR-REL-001(영속성 — **BLOCKED**), NFR-REL-003(정원 원자성 — 저장소 계약만), NFR-REL-005(페이지네이션, 프로필 배치 조회), NFR-UX-001(로딩/빈/오류/연결준비 상태).

## 2. 변경 파일

- `services/api/app/features/community/domain.py` — `CommunityActor`, 상태 enum, 전이표, 정원(모집자 포함) 계산, 서버 시각 마감 판정, 지원 사전검사.
- `services/api/app/features/community/schemas.py` — 요청 DTO(`extra="forbid"`로 `author_id`/`owner_id`/`status`/`accepted_count`/`is_mine` 주입 400), 응답 DTO(익명 글에 author/user/identity 필드 없음, 표시명 `익명` 고정; 모집은 `owner.display_name`만).
- `services/api/app/features/community/repository.py` — `AnonymousPostRepository`, `RecruitmentRepository`, `PublicProfileReader` Protocol과 구현 의무(비공개 원장+공개 모델 동일 트랜잭션, revision CAS, 공개 조회 private join 금지, 승인 시 행 잠금).
- `services/api/app/features/community/service.py` — `AnonymousPostService`, `RecruitmentService`.
- `services/api/app/features/community/router.py`, `__init__.py` — `create_community_router(CommunityDependencies)` 팩토리와 기본 `router`.
- `services/api/app/features/community/idempotency.py` — (2차) 생성 멱등 claim·digest·replay 판정.
- `services/api/tests/test_community_domain.py`, `services/api/tests/test_community_http.py`, `services/api/tests/test_community_idempotency.py`(2차) — 테스트(테스트 전용 메모리 fake).
- `apps/web/src/features/community/` — `index.tsx`(default export), `AnonymousBoard.tsx`, `RecruitmentBoard.tsx`, `StatusPanel.tsx`, `useRemoteList.ts`, `api.ts`, `types.ts`, (2차) `api.test.ts`, `index.test.tsx`.

## 3. API 계약 (마운트 전, root가 `/api/v1` prefix로 include 예정)

| 메서드·경로 | 동작 | 주요 오류 |
| --- | --- | --- |
| `GET /anonymous-posts?limit&offset` | 활성 글 목록, `is_mine`은 서버 계산 | 401/403, limit>50 → 400 |
| `GET /anonymous-posts/{id}` | 활성 글 | 비활성/없음 404 |
| `POST /anonymous-posts` `{title, body}` + `Idempotency-Key` 필수 | 201 생성(재요청은 201 + `Idempotent-Replayed: true`) | 제목 2~120, 본문 1~5000, 추가 필드·키 누락/형식 오류 400, 같은 키 다른 본문 409 |
| `PATCH /anonymous-posts/{id}` `{revision, title?, body?}` | 본인만 수정 | 타인/비활성 404, revision 불일치 409 |
| `DELETE /anonymous-posts/{id}?revision=` | 본인만 `deleted` 전환, 공개 모델 제거 | 타인 404, 충돌 409 |
| `GET /recruitments`, `GET /recruitments/{id}` | 실명 프로필 이름·상태(서버 시각 기준 마감 반영) | 없음 404 |
| `POST /recruitments` + `Idempotency-Key` 필수 | `{title, body, field, roles[1~10], capacity 2~20, deadline_at(타임존 필수, 미래), opportunity_id?}` | 400, 같은 키 다른 본문 409, 연결 불가 `opportunity_id` 400 |
| `PATCH /recruitments/{id}` | 모집자만, `open`이고 마감 전에만 | 타인 404, 마감/종료 409, 정원 < 1+승인수 409 |
| `POST /recruitments/{id}/close` `{revision}` | `open→closed` | 재마감·충돌 409 |

응답은 `app.schemas.common.SuccessResponse`(`data`/`resource_version`=revision/`server_time`), 오류는 공통 `ErrorResponse`. 타인 자원 변경은 존재 노출 방지를 위해 404로 응답한다(P0 계약). `cancel`은 서비스에만 있고 라우트는 계약에 없어 노출하지 않았다. **모집글 삭제 API/UI는 삭제 정책 미확정으로 계속 차단**(마감만 제공).

### 3.1 멱등 생성 계약 (`app/features/community/idempotency.py`)

- 범위: `(actor user_id, method=POST, canonical path, key)` — PR #13 `IdempotencyScope`(main 미병합)와 같은 구조를 기능 내부에 둠. 공통 스키마는 수정하지 않음. canonical path는 `/api/v1/anonymous-posts`, `/api/v1/recruitments` 고정.
- 키: `Idempotency-Key` 헤더, 출력 가능 ASCII 1~128자(`^[!-~]{1,128}$`). 생성 POST에서 필수(자연 유일키가 없음). 인증 판정(401/403)이 키 검증보다 먼저.
- 본문 digest: 검증·정규화된 본문(`model_dump(mode="json")`, 키 정렬)의 SHA-256. 앞뒤 공백만 다른 재시도는 같은 요청.
- 원자 저장: 저장소 `create(resource, claim) -> claim`이 claim·비공개 원장·공개 투영을 **한 트랜잭션**에 쓰고, namespace 유일키 충돌이면 아무것도 쓰지 않고 기존 claim을 반환(동시 경합 포함). 서비스가 digest 비교 → 같으면 replay, 다르면 409, 다른 scope의 claim이 오면 500(실패닫힘).
- replay: 매 요청 actor 의존성이 **현재 권한을 재판정**(권한 회수 시 403)하고, 저장된 결과를 그대로 내지 않고 `get`으로 **현재 상태·가시성**을 다시 읽는다(수정 후 replay는 최신 revision, 삭제 후 replay는 404 — 재생성·부활 없음).
- revision과 독립: PATCH/DELETE/close는 기존 revision CAS만 사용하며, 키를 보내도 무시되어 stale revision은 그대로 409.
- 미결(DB 담당): claim 보존 기간/TTL, 테이블 설계. 자동 확정하지 않음.

### 3.2 캐시·기회 연결

- 모든 커뮤니티 라우트 응답(성공)에 `Cache-Control: private, no-store` — `is_mine`이 호출자마다 다르므로 공유/브라우저 캐시 재사용 금지. 계정 A/B 각각 헤더와 다른 `is_mine`을 HTTP 테스트로 확인.
- `opportunity_id`: `OpportunityVisibility.is_linkable(actor_id, opportunity_id)` seam. 기본 공급자는 없음(`None`) → `opportunity_id`를 보낸 생성은 **400으로 거부**, 미지정 생성은 정상. 없음/비공개는 같은 400 본문(존재 추측 불가). 기회 담당이 공급자를 주입해야 연결 가능.
- 정원 상한 20(모집자 포함)은 **시연 설계 기본값**이며 승인된 정책 값이 아니다(`domain.py`, `types.ts` 주석).

## 4. 연결 차단 기록 (root/공통 담당 처리 필요)

1. **라우터 미마운트**: `app/api/v1/router.py`/`factory.py`는 수정 금지라 포함하지 않았다. root가 `app.include_router(create_community_router(deps), prefix="/api/v1")`로 연결해야 한다. 마운트 시 `tests/test_foundation.py::test_openapi_matches_runtime`의 경로 집합 단언, `openapi.json` 스냅샷, 프런트 생성 타입을 root가 함께 갱신해야 한다.
2. **인증 BLOCKED**: 기본 `actor` 의존성은 503 `UNAVAILABLE`로 실패닫힘. 인증 담당자가 서버 검증된 `CommunityActor(user_id, community_access)`를 반환하는 의존성(미인증은 `None`→401, 권한 없음→403)을 주입해야 한다. `community_access`는 서버 역할 데이터로만 계산.
3. **DB BLOCKED**: MariaDB 모델·마이그레이션·저장소 구현 없음. 기본 저장소 의존성은 503. Protocol 주석의 원자성·CAS·private/public 분리를 만족해야 한다. MariaDB에는 PostgreSQL RLS가 없으므로 공개 모델 분리와 DB 계정 권한으로 대체 설계가 필요하다(공통 DB 담당 결정).
4. **CORS**: 공통 `factory.py`의 CORS가 `GET`·`Content-Type`만 허용한다. 교차 출처 배포라면 POST/PATCH/DELETE와 `Idempotency-Key` 요청 헤더, `Idempotent-Replayed` 노출 헤더를 root가 결정해야 한다(같은 출처 프록시면 불필요).
4-1. **멱등 claim 저장소**: DB 담당이 namespace 유일키 + 자원 행 동일 트랜잭션 + 보존 기간을 구현해야 한다(3.1).
4-2. **기회 가시성 공급자**: 기회 담당이 `OpportunityVisibility`를 주입하기 전까지 모집글의 기회 연결은 거부된다.
5. **요청 제한(NFR-SEC-006)** 미구현 — 공통 미들웨어 담당.
6. **FR-COM-005 지원·승인**: 지원 테이블·멱등 키·행 잠금 저장소가 필요해 API 미노출. 도메인 사전검사만 있음.
7. **익명 신고 시 작성자 매핑 접근 절차**(FR-COM-003, RBAC) 미결정 — 운영자 신원 조회 경로 없음.

## 5. 실제 검증

### 5.1 2차(리뷰 결함 수정 후, `origin/main` 병합 트리, 2026-10-30)

| 위치 | 명령 | 결과 |
| --- | --- | --- |
| `services/api` | `uv sync --locked` (uv `C:/DIT CSW/ditNow-python-tools/Scripts/uv.exe`) | 성공 |
| `services/api` | `uv run --locked ruff check .` | `All checks passed!` |
| `services/api` | `uv run --locked ruff format --check .` | `38 files already formatted` |
| `services/api` | `uv run --locked pytest -q` | **162 passed**(병합 직후 기준선 127 → 커뮤니티 회귀 35개 추가), 경고 1(httpx/starlette deprecation) |
| `apps/web` | `npm ci` | 성공, 0 vulnerabilities |
| `apps/web` | `npm run api:types:check` | `New web API types match the public server snapshot.` |
| `apps/web` | `npm run typecheck` | 오류 없음 |
| `apps/web` | `npm test` | **4 files / 47 passed**(커뮤니티 `api.test.ts`·`index.test.tsx` 포함) |
| `apps/web` | `npm run build` | 성공. 단 공통 셸 `App.tsx`가 커뮤니티 기능을 아직 import하지 않아 **번들에는 미포함**(타입체크·Vitest로만 검증) |
| 루트 | `node scripts/check-agent-config.mjs` | PASS |
| 변이 확인 | `api.ts`의 `BASE`를 `"/api/v1"`로 되돌려 `npm test` | 4 tests 실패(이중 prefix 검출) 확인 후 원복 |

신규 회귀(백엔드): 같은 키·본문 2회 → 같은 ID 1건(글/모집), 정규화 동일 본문 replay, 같은 키 다른 본문 409, actor/path별 키 분리, 키 누락·공백·비ASCII·129자 400(저장 없음), 미인증+키 누락 401 우선, 권한 회수 후 replay 403, replay 시 현재 revision·삭제 후 404, revision CAS와 키 독립, 경합 패배 시 승자 replay/다른 본문 409, 타 scope claim 반환 시 500 실패닫힘, 계정 A/B `Cache-Control: private, no-store`, 기회 공급자 없음 400·없음/숨김 동일 400.
신규 회귀(프런트, 실제 공유 client + fetch stub): 모든 엔드포인트 최종 URL이 `/api/v1` 한 번, 절대 base 설정 시도 한 번, 생성에만 `Idempotency-Key`, 로딩/503 재시도/401/500(요청 ID), 네트워크 실패 후 같은 입력 재시도는 같은 키·입력 변경 시 새 키, 클라이언트 검증 실패 시 요청 없음, 모집 수정은 변경 필드+revision만 PATCH·무변경 차단·409 안내, 타인 모집에는 수정/마감 없음·삭제 버튼 없음.

### 5.2 미검증 / 게이트

- **NOT_RUN(DB)**: 실제 DB(MariaDB 11.4, 팀원 Proxmox VM, Tailscale private 3307)는 연결하지 않았다. 앱 DML 전용/마이그레이터 DDL 분리 계정, 저장소 구현, claim 테이블, 통합 테스트 모두 미실행. 로컬 DB 컨테이너 생성·운영 접속·마이그레이션 시도 없음. 위 결과는 모두 테스트 전용 fake 기반 단위/HTTP 계약 검증이다.
- **NOT_RUN(브라우저 E2E)**: 2계정 브라우저 시나리오(TC-V1-COM-001/004), TC-V1-COM-005.
- **사람 승인 게이트**: 라우터 마운트·OpenAPI 스냅샷 갱신(root), 인증 공급자·교직원 범위 활성화(차단 유지), CORS, claim 보존 기간, 정원 상한·모집 삭제 정책, merge/deploy.
- **CI**: 이 세션에는 CI 조회 도구 권한이 없어 PR HEAD의 GitHub Actions 결과를 확인하지 못했다 — root가 확인해야 한다.

### 5.3 1차 (병합 전, 기록 보존)

| 명령 | 결과 |
| --- | --- |
| `uv sync --locked` | 성공 |
| `uv run --locked ruff check .` | `All checks passed!` |
| `uv run --locked ruff format --check .` | `30 files already formatted` |
| `uv run --locked pytest -q` | 114 passed (기존 테스트 무수정 포함), 경고 1(httpx/starlette deprecation) |

검증된 동작(단위/HTTP 계약, 테스트 전용 fake 저장소): 기본 라우터 503 실패닫힘, 미인증 401·미승인 403, 인증이 저장소 접근보다 먼저 판정, 익명 CRUD와 공개 JSON에 내부 UID·실명·`author_id`/`owner_id` 부재, 작성자 필드 주입 400, 제목/본문 경계값·제어문자·줄바꿈 제목 거부, 타인 수정/삭제 404, revision 충돌 409, 숨김 글 비공개, `<script>`가 텍스트로만 반환, 페이지네이션, 모집 CRUD·마감·재마감 409·마감 후 수정 409, 서버 시각 마감 판정, 정원 경계(2~20, 모집자 포함, 1+승인수 미만 축소 409), 익명 글과 모집 사이 공유 식별자 없음(TC-V1-X02 단위 수준), OpenAPI 스키마에 익명 식별 필드 없음.

## 6. 상태 구분

- **IMPLEMENTED(부분)**: FR-COM-001, FR-COM-004 기능 패키지·프런트 소스. FR-COM-005 도메인 규칙만.
- **TESTED(unit)**: 위 5절 백엔드 단위/HTTP 계약 테스트.
- **BLOCKED(DB/auth)**: 실제 영속성(NFR-REL-001), 동시 승인 원자성(NFR-REL-003), 인증 공급자, 앱 마운트.
- **TESTED(FE unit)**: `apps/web`이 main에 병합되어 타입체크·Vitest 실행(5.1). 셸 라우트 연결(`App.tsx`)은 공통 소유라 미연결.
- **NOT_RUN**: TC-V1-COM-001/004의 2계정 브라우저·DB 시나리오, TC-V1-COM-005, 실제 DB.
- 전체 FR **VERIFIED 아님**.

## 7. 프런트 동작 원칙

- `requestData<T>`/`ApiError(code/status/requestId)`를 `../../lib/api`에서 가져온다. 공유 client가 기본 base `/api/v1`을 붙이므로 기능 경로는 `/anonymous-posts`처럼 base 상대로만 쓴다(`BASE = ""`; 이전 `"/api/v1"`은 `/api/v1/api/v1/...` 결함).
- 생성 요청마다 `Idempotency-Key`(UUID)를 보낸다. 실패 후 같은 입력으로 다시 누르면 같은 키를 재사용하고, 입력을 바꾸거나 성공하면 새 키를 만든다.
- 모집자는 `open` 모집글을 수정할 수 있다(변경 필드만 + 현재 revision). 삭제 UI는 없다.
- 404/503/네트워크 오류는 "연결 준비 중", 401은 로그인 필요, 403은 권한 미확인으로 표시. 목업 데이터·localStorage 대체 없음. 연결 전에는 등록 버튼 비활성.
- 변경 성공 후에는 낙관적 갱신 없이 서버 목록을 다시 불러온다. "저장 완료" 문구를 쓰지 않는다(DB 영속 확인 전).
- 본문은 React 텍스트 노드로만 렌더링(`dangerouslySetInnerHTML` 없음). 익명 글 타입에 작성자 필드 없음.

## 8. 독립 리뷰 결함별 조치 (2차)

| 결함 | 조치 | 검증 |
| --- | --- | --- |
| FE `BASE='/api/v1'` + 공유 client 기본 base → 이중 prefix | `BASE = ""` | 실제 client+fetch stub URL 테스트, 변이 시 실패 확인 |
| 생성 POST가 `Idempotency-Key` 무시(같은 키 2회 → 서로 다른 ID) | 키 필수, scope·digest·원자 claim Protocol, replay 권한·가시성 재검증 | `test_community_http.py`, `test_community_idempotency.py` |
| GET 응답의 `is_mine` 캐시 위험 | 라우터 전역 `Cache-Control: private, no-store` | 계정 A/B 헤더 테스트 |
| `opportunity_id` 존재/가시성 미검사 | `OpportunityVisibility` seam, 공급자 없으면 거부, 없음/숨김 동일 응답 | HTTP·unit 테스트 |
| 모집 수정 FE 누락 | 소유자 `open` 모집 수정 폼, 변경 필드만 PATCH; 삭제 차단 유지 | `index.test.tsx` |
| 정원 20 근거 불명 | 시연 설계 기본값으로 명시(정책 확정 아님) | 문서·주석 |
| UI 상태 테스트 부재 | 로딩/503 재시도/401/500/입력 재시도 Vitest | `index.test.tsx` |

## 9. 다음 실행 가능 태스크

1. root: 라우터 마운트 + OpenAPI 스냅샷/foundation 테스트/프런트 생성 타입 갱신 + CORS 결정.
2. 인증 담당: `CommunityActor` 공급 의존성.
3. DB 담당: `anonymous_posts_private/public`, `recruitments` 마이그레이션과 Protocol 구현, 실제 DB 통합 테스트.
4. FR-COM-005 지원·승인 API(P1) — 3 이후.
