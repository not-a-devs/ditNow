# TASK-COMMUNITY — 익명 게시글과 실명 모집 1차 구현 기록

- 작성일: 2026-10-30
- 브랜치: `feat/community-recruitment-firstpass-20261030` (독립 worktree)
- 상태: `review` — 기능 패키지·단위/HTTP 계약 테스트만 완료. **공통 앱 미연결(라우터 미마운트), DB·인증 미연결.**
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
- `services/api/tests/test_community_domain.py`, `services/api/tests/test_community_http.py` — 신규 테스트(테스트 전용 메모리 fake).
- `apps/web/src/features/community/` — `index.tsx`(default export), `AnonymousBoard.tsx`, `RecruitmentBoard.tsx`, `StatusPanel.tsx`, `useRemoteList.ts`, `api.ts`, `types.ts`.

## 3. API 계약 (마운트 전, root가 `/api/v1` prefix로 include 예정)

| 메서드·경로 | 동작 | 주요 오류 |
| --- | --- | --- |
| `GET /anonymous-posts?limit&offset` | 활성 글 목록, `is_mine`은 서버 계산 | 401/403, limit>50 → 400 |
| `GET /anonymous-posts/{id}` | 활성 글 | 비활성/없음 404 |
| `POST /anonymous-posts` `{title, body}` | 201 생성 | 제목 2~120, 본문 1~5000, 추가 필드 400 |
| `PATCH /anonymous-posts/{id}` `{revision, title?, body?}` | 본인만 수정 | 타인/비활성 404, revision 불일치 409 |
| `DELETE /anonymous-posts/{id}?revision=` | 본인만 `deleted` 전환, 공개 모델 제거 | 타인 404, 충돌 409 |
| `GET /recruitments`, `GET /recruitments/{id}` | 실명 프로필 이름·상태(서버 시각 기준 마감 반영) | 없음 404 |
| `POST /recruitments` | `{title, body, field, roles[1~10], capacity 2~20, deadline_at(타임존 필수, 미래), opportunity_id?}` | 400 |
| `PATCH /recruitments/{id}` | 모집자만, `open`이고 마감 전에만 | 타인 404, 마감/종료 409, 정원 < 1+승인수 409 |
| `POST /recruitments/{id}/close` `{revision}` | `open→closed` | 재마감·충돌 409 |

응답은 `app.schemas.common.SuccessResponse`(`data`/`resource_version`=revision/`server_time`), 오류는 공통 `ErrorResponse`. 타인 자원 변경은 존재 노출 방지를 위해 404로 응답한다(P0 계약). `cancel`은 서비스에만 있고 라우트는 계약에 없어 노출하지 않았다.

## 4. 연결 차단 기록 (root/공통 담당 처리 필요)

1. **라우터 미마운트**: `app/api/v1/router.py`/`factory.py`는 수정 금지라 포함하지 않았다. root가 `app.include_router(create_community_router(deps), prefix="/api/v1")`로 연결해야 한다. 마운트 시 `tests/test_foundation.py::test_openapi_matches_runtime`의 경로 집합 단언, `openapi.json` 스냅샷, 프런트 생성 타입을 root가 함께 갱신해야 한다.
2. **인증 BLOCKED**: 기본 `actor` 의존성은 503 `UNAVAILABLE`로 실패닫힘. 인증 담당자가 서버 검증된 `CommunityActor(user_id, community_access)`를 반환하는 의존성(미인증은 `None`→401, 권한 없음→403)을 주입해야 한다. `community_access`는 서버 역할 데이터로만 계산.
3. **DB BLOCKED**: MariaDB 모델·마이그레이션·저장소 구현 없음. 기본 저장소 의존성은 503. Protocol 주석의 원자성·CAS·private/public 분리를 만족해야 한다. MariaDB에는 PostgreSQL RLS가 없으므로 공개 모델 분리와 DB 계정 권한으로 대체 설계가 필요하다(공통 DB 담당 결정).
4. **CORS**: 공통 `factory.py`의 CORS가 `GET`만 허용한다. 브라우저에서 POST/PATCH/DELETE를 쓰려면 root가 허용 메서드·헤더를 결정해야 한다.
5. **요청 제한(NFR-SEC-006)** 미구현 — 공통 미들웨어 담당.
6. **FR-COM-005 지원·승인**: 지원 테이블·멱등 키·행 잠금 저장소가 필요해 API 미노출. 도메인 사전검사만 있음.
7. **익명 신고 시 작성자 매핑 접근 절차**(FR-COM-003, RBAC) 미결정 — 운영자 신원 조회 경로 없음.

## 5. 실제 검증 (2026-10-30, `services/api`, uv `C:/DIT CSW/ditNow-python-tools/Scripts/uv.exe`)

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
- **NOT_RUN(FE 통합)**: `apps/web` 패키지·shell·`src/lib/api.ts`가 다른 브랜치에서 작성 중이라 타입체크·빌드·브라우저 테스트 미실행. npm 설치 안 함. TC-V1-COM-001/004의 2계정 브라우저·DB 시나리오, TC-V1-COM-005 미실행.
- 전체 FR **VERIFIED 아님**.

## 7. 프런트 동작 원칙

- `requestData<T>`/`ApiError(code/status/requestId)`를 `../../lib/api`에서 가져온다(공통 브랜치 계약 가정).
- 404/503/네트워크 오류는 "연결 준비 중", 401은 로그인 필요, 403은 권한 미확인으로 표시. 목업 데이터·localStorage 대체 없음. 연결 전에는 등록 버튼 비활성.
- 변경 성공 후에는 낙관적 갱신 없이 서버 목록을 다시 불러온다. "저장 완료" 문구를 쓰지 않는다(DB 영속 확인 전).
- 본문은 React 텍스트 노드로만 렌더링(`dangerouslySetInnerHTML` 없음). 익명 글 타입에 작성자 필드 없음.

## 8. 다음 실행 가능 태스크

1. root: 라우터 마운트 + OpenAPI 스냅샷/foundation 테스트/프런트 생성 타입 갱신 + CORS 결정.
2. 인증 담당: `CommunityActor` 공급 의존성.
3. DB 담당: `anonymous_posts_private/public`, `recruitments` 마이그레이션과 Protocol 구현, 실제 DB 통합 테스트.
4. FR-COM-005 지원·승인 API(P1) — 3 이후.
