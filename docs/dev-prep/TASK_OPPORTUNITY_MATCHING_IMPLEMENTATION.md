# TASK-V — 학과·학년·관심사 맞춤 기회 조회 1차 구현 (비활성)

2026-10-30 KST · 브랜치 `feat/opportunity-matching-firstpass-20261030` · 상태: **review (공통 미연결, 기본 503)**

이 문서는 FR-OPP-002 맞춤 공고 조회와, 승인 범위 안의 FR-AI-002/003 **규칙 기반 부분**의 실제 구현·검증 상태를 기록한다. 앱 라우터 집계·인증·DB·OpenAPI 스냅샷·프런트 shell 연결은 root 소관이며 수정하지 않았다. 어떤 FR도 VERIFIED로 주장하지 않으며 실제 DB 검증은 하지 않았다.

## 1. 근거와 범위

| 구분 | ID | 이 작업에서 다룬 범위 |
|---|---|---|
| FR | FR-OPP-002 | 현재 소속 학과·학년 + 요청에 담긴 관심사로 기존 승인 공고를 규칙 기반 정렬·필터 |
| FR (부분) | FR-AI-002 | 원문 필드·고정 절차 템플릿·근거 필드로 구성한 구조화 요약. **문장 생성·요약 재작성·LLM 없음** |
| FR (부분) | FR-AI-003 | 관심 분류·키워드 일치 근거 표시, 공고에 연결된 팀원 모집 참조(seam)와 키워드 관련도 표시. **학습형 추천·외부 추천 업체 없음** |
| 근거 문서 | `docs/02_FRD.md` §FR-OPP-001~004·§FR-AI-001~003, `docs/03_NFR.md` NFR-AI-001~004, `docs/v1-draft/04_RBAC.md` RBAC-OPP/RBAC-AI, `docs/dev-prep/TASK_OPPORTUNITIES_IMPLEMENTATION.md` | |
| TC | TC-V1-OPP-002(부분), TC-V1-AI-002/003(규칙 부분) | 실제 2계정·실DB는 NOT_RUN |

FRD §FR-AI-001~003은 "서버가 정해진 규칙으로 기간·마감·대상을 계산하고 AI는 설명을 생성"한다고 정한다. 이 작업은 **서버 규칙 부분만** 구현했다. AI 설명 생성(LLM 호출·스키마 검증·429·프롬프트 주입 방어)은 장기 범위로 남는다(§6).

## 2. 변경 파일

- `services/api/app/features/opportunity_matching/`
  - `ports.py` — `AcademicContextReader`(검증된 행위자의 *현재* 승인 소속 읽기), `RecruitmentReferenceReader`(선택 seam, 요청 행위자의 `CommunityActor`를 받음). 운영 어댑터 없음.
  - `models.py` — 응답 DTO. 공고 필드는 API-OPP `OpportunitySummaryData`/`OpportunityDetailData` 재사용.
  - `service.py` — 결정적 규칙 엔진, 후보 상한·완료 플래그, 안정 정렬·커서, 비정상 행 제외, 구조화 요약.
  - `router.py`, `__init__.py` — `create_router(MatchingDependencies)`와 기본 `router`(실패 닫힘).
- `services/api/tests/test_opportunity_matching_support.py`(테스트 전용 fake), `test_opportunity_matching_service.py`(27), `test_opportunity_matching_http.py`(21)
- `apps/web/src/features/opportunity-matching/` — `types.ts`, `api.ts`, `labels.ts`, `index.tsx`(default 컴포넌트), `api.test.ts`(15), `index.test.tsx`(16)
- 리뷰 수정에서 root가 이 작업에 넘긴 공유 범위: `services/api/app/features/opportunities/service.py`의 `safe_url`과 `tests/test_opportunities_service.py`의 URL 테스트만
- 이 문서

## 3. 재사용(중복 없음)

| 재사용 대상 | 용도 |
|---|---|
| `opportunities.repository.OpportunityCatalog`·`OpportunityQuery` | 유일한 공고 원천. 같은 공고 ID, 별도 저장·수집 없음 |
| `opportunities.service.matches`·`to_summary`·`to_detail`·`safe_url`·`MAX_LIMIT` | 공개 여부 방어 재필터, 응답 projection, http(s) 외 URL 제거 |
| `opportunities.dependencies.Principal`·`auth_not_configured`·`catalog_not_configured` | 인증 주입점과 503 기본값 |
| `community.domain.Recruitment`·`effective_status`·`has_open_seat` | 모집 마감·정원 판정(서버 시각, 커뮤니티와 같은 규칙) |
| `community.domain.CommunityActor`·`require_member` | 모집 참조 전에 커뮤니티 라우트와 같은 권한 검사 |
| `campus.domain.MIN_GRADE`·`MAX_GRADE` | 학년 입력 범위 |
| `collaboration.router.PrivateNoStoreRoute` | 성공·오류 응답 모두 `private, no-store` |
| FE `opportunities/types`·`status`(`KIND_LABEL`, `formatDateTime`), 공유 `lib/api.requestData` | 타입·표시·전송 |

`PrivateNoStoreRoute`는 이미 여러 feature에 같은 코드가 있어, 새 사본을 만들지 않고 collaboration의 것을 import했다. 예상외 오류 로그 이벤트명이 `collaboration.request.failed`로 남는 한계가 있어 root가 `app/core`로 승격하는 것을 권장한다(공통 파일이라 이 작업에서 수정하지 않음).

## 4. 구현된 계약 (root mount 후 `/api/v1` 접두)

| 메서드·경로 | 권한 | 동작 |
|---|---|---|
| `GET /me/opportunity-matches?interest_kind*&interest_keyword*&kind&include_closed&limit&cursor` | 검증된 본인 + 현재 소속 | 승인 공고 중 현재 소속 범위에 드는 것만, 점수·근거·기간·신선도·출처·모집 참조 포함 |
| `GET /me/opportunity-matches/{id}/brief?interest_kind*&interest_keyword*` | 검증된 본인 + 현재 소속 | 원문 필드·절차 템플릿·근거·주의 사항. 범위 밖 공고도 공개 공고면 `OUT_OF_SCOPE` 주의와 함께 표시 |

규칙(시연 설계 기본값, 학교 승인 정책 아님):

- 대상 범위: `school`→`SCHOOL_WIDE`(10), `department`→소속 학과 포함 시 `DEPARTMENT_MATCH`(20), `grade`→**같은 소속 행**의 학과·학년이 모두 맞을 때 `GRADE_MATCH`(30)(+학과 지정 시 `DEPARTMENT_MATCH`). 학과 A·학년 1과 학과 B·학년 2를 섞어 맞추지 않는다. 범위 밖은 목록에서 제외.
- 관심사: 분류 일치 `KIND_INTEREST`(15), 키워드가 제목→주관→자격 원문 순으로 포함되면 `KEYWORD_INTEREST`(10, 점수는 최대 2개). 관심사는 요청 입력일 뿐 저장하지 않으며 새 프로필을 만들지 않는다. 최대 5개·키워드 1~20 **코드 포인트**(이모지 1개 = 1자)·`str.isprintable()` 실패(제어·서식·NBSP·ZWJ 등) 거부(400).
- `DEADLINE_SOON`(5): 접수 중이고 마감 7일 이내.
- 기간 `UPCOMING/OPEN/CLOSED/NO_DEADLINE`(서버 시각), 마감 공고는 `include_closed=true`일 때만.
- 신선도: `checked_at` 없음 `UNVERIFIED`, 30일 초과 `STALE`, 그 외 `CURRENT`.
- 정렬: 점수 내림차순 → 마감 오름차순(없음은 뒤) → ID. 커서 `"{offset}.{digest}"`의 digest는 행위자 ID+정규화된 현재 소속+요청 조건+순위 목록(ID·점수) 스냅샷의 해시라, 다른 행위자가 재사용하거나 소속·조건·카탈로그가 바뀌면 409(건너뛰기·중복 대신 재시작 요구). 순위가 같아도 행위자·소속이 다르면 409다.
- 후보 상한: 카탈로그 페이지(50) 단위로 최대 200건. 상한 도달·반복 커서·페이지 크기 위반이면 `complete=false`.
- 비정상 행(naive 시각, 시작>마감, 미래 확인 시각, 빈 제목, 범위·학년 형식 오류, 중복 ID, projection 검증 실패)은 제외하고 `omitted_count`만 반환한다. 제목·ID 등 메타데이터는 내보내지 않는다. 공개(`PUBLISHED`)가 아닌 행은 중복 판정·`omitted_count`·`candidates_scanned` 계산 **전에** 버려 세지도 않는다(비공개 행 존재를 수로 추론 불가). `candidates_scanned`는 공개 행 수다. 요약 API에서는 부재와 같은 404.
- 신원: 소속은 `AcademicContextReader.current(principal.user_id)`로만 읽고, 반환 `user_id`가 principal과 다르거나 None이면 403. 쿼리의 `user_id`/`department`는 무시된다. 형식이 잘못된 소속 행은 버린다.
- 출처 표시: `provenance={generator:"deterministic_rules_v1", ai_generated:false, eligibility_guaranteed:false, notice}`, 모든 근거에 `source_field`. 절차 단계마다 `evidence_field`/값/안전 URL, 정보 없으면 `available=false`(지어내지 않음). 요약의 자격 문구는 원문 그대로.
- 모집 seam: 모집은 커뮤니티 데이터다. 요청마다 커뮤니티 인증 소유자가 서버에서 새로 판정한 `CommunityActor`를 `community_actor` 의존성으로 받아, 커뮤니티 라우트와 같은 `require_member`(`community_access`)를 통과하고 그 `user_id`가 검증된 principal과 같을 때만 어댑터를 호출하며 그 actor를 어댑터에 넘긴다(행위자 범위 조회). **학적 소속만으로는 커뮤니티 권한이 생기지 않는다.** actor 미주입·권한 없음·타인 actor·형식 오류는 어댑터를 호출하지 않고 `NOT_CONNECTED`(모집 메타데이터 없음), 어댑터 미주입도 `NOT_CONNECTED`, 어댑터 예외 `UNAVAILABLE`(상세 미노출, 목록은 계속 동작). 연결 시 마감 전 `open`이고 **빈자리가 있는**(`has_open_seat`) 모집만 id·제목·분야·역할·마감·일치 키워드로 투영(작성자·본문·지원자·인원 미노출), 공고당 최대 3건과 총수.
- URL: API-OPP `safe_url`은 http(s) 절대 URL만 통과시키고 사용자 정보(`user`, `:secret`, 빈 자격 증명 포함 `@` 전부)가 있으면 버린다. 목록 `source_url`·요약 `evidence_url`에 자격 증명이 실리지 않는다.
- 모든 응답(오류 포함) `Cache-Control: private, no-store`. FE도 `cache: 'no-store'`.

프런트: 실제 계약 client(`api.ts`)로 목록·요약을 호출하고 서버 응답만 표시한다. 로딩·503·401·403·400·네트워크 재시도·빈 결과·`complete=false`·`omitted_count`·신선도 경고·DEMO 표시·근거·절차·주의·모집 상태를 구분한다. 늦게 도착한 이전 요청 응답은 순번으로 무시하고, 대체된 요청과 언마운트 시 남은 요청은 `AbortController`로 중단한다. 더 보기 409는 "처음부터 다시 불러오기"를 제공한다. 관심 키워드는 서버와 같은 규칙(코드 포인트 20자·isprintable 대응 정규식·최대 5개)으로 검사해 위반 시 **자르거나 바꾸지 않고** 입력란 아래 구체적 오류(`role=alert`, `aria-invalid`)를 보여 주며 요청을 보내지 않는다. 링크는 http(s)·자격 증명 없는 URL만 `noopener noreferrer`로 렌더링한다.

## 5. root 통합 방법

```python
from app.features.opportunity_matching import MatchingDependencies, create_router
router.include_router(create_router(MatchingDependencies(
    current_principal=<공통 인증 → Principal(user_id)>,
    academic_context=<현재 승인 소속 읽기: 같은 요청/트랜잭션에서 학과 UUID→카탈로그 학과 코드 매핑>,
    catalog=<API-OPP와 같은 승인 공개 projection>,
    recruitments=<선택: community 모집 목록 어댑터(actor 범위), 없으면 생략>,
    community_actor=<선택: community 인증 소유자의 요청별 CommunityActor 판정, 권한 없으면 None 반환>,
)))
```

`community_actor`를 학적 소속 존재 여부로 만들어서는 안 된다. 미주입 시 모집 참조는 항상 `NOT_CONNECTED`다.

## 6. 상태와 남은 게이트

| 항목 | 상태 |
|---|---|
| 규칙 엔진·DTO·주입형 라우터 | IMPLEMENTED (부분) |
| 서비스·HTTP 계약 | TESTED (unit, 메모리 fake + TestClient) |
| FE client·UI 상태 | TESTED (Vitest, jsdom). 브라우저 E2E NOT_RUN |
| 공통 인증·현재 소속 원장 어댑터 | **BLOCKED** (OPEN-002/003, 공통 auth/DB 소유자). 기본 503 |
| 실제 MariaDB 조회·학과 코드 매핑 | **NOT_RUN DB** — 접속·migration·신규 테이블 없음 |
| 앱 라우터 mount·OpenAPI 스냅샷·FE 생성 타입·shell 메뉴 | NOT_RUN (root 통합). 기능 모듈은 번들에 미포함 |
| 모집 seam 실제 어댑터·커뮤니티 actor 판정 | NOT_RUN (community 저장소·인증 연결 후). 기본은 `NOT_CONNECTED` |
| FR-AI-002/003 LLM 설명 생성 | **범위 밖(장기)**. 실제 LLM 호출 없음, 비용·한도·스키마 검증·프롬프트 주입 테스트는 해당 태스크에서 |
| 점수·30일·7일·200건 값 | 시연 설계 기본값, 학교 정책 승인 필요 |
| TC-V1-OPP-002 2계정·실DB | NOT_RUN |

## 7. 실제 실행한 검증 (로컬 Windows, 2026-10-30)

| 위치 | 명령 | 결과 |
|---|---|---|
| `services/api` | `uv sync --locked` | 성공 |
| `services/api` | `uv run --locked pytest -q tests/test_opportunity_matching_service.py` | 18 passed |
| `services/api` | `uv run --locked pytest -q tests/test_opportunity_matching_http.py` | 17 passed |
| `services/api` | `uv run --locked ruff check .` / `ruff format --check .` | All checks passed / 136 files already formatted |
| `services/api` | `uv run --locked pytest -q` | 714 passed, 기존 httpx 경고 1건 |
| `apps/web` | `npm ci` | 성공 |
| `apps/web` | `npm test -- src/features/opportunity-matching` | 2 files, 19 passed |
| `apps/web` | `npm run typecheck`, `npm run api:types:check` | 오류 없음 / 공개 스냅샷 일치 |
| `apps/web` | `npm test` | 23 files, 319 passed |
| `apps/web` | `npm run build` | 성공 |

### 7.1 독립 리뷰 수정 후 (같은 날)

독립 리뷰(M1·M2·L3~L6, I2)를 코드에서 재확인한 뒤 수정했다. 수정 전 기준선: 대상 3개 파일 `pytest` 91 passed.

| 위치 | 명령 | 결과 |
|---|---|---|
| `services/api` | `uv run --locked pytest -q tests/test_opportunity_matching_service.py tests/test_opportunity_matching_http.py tests/test_opportunities_service.py` | 112 passed (27 + 21 + 64) |
| `services/api` | `uv run --locked ruff check .` / `ruff format --check .` | All checks passed / 136 files already formatted |
| `services/api` | `uv run --locked pytest -q` | 735 passed, 기존 httpx 경고 1건 |
| `apps/web` | `npm test -- src/features/opportunity-matching` | 2 files, 31 passed |
| `apps/web` | `npm run typecheck` / `npm run build` | 오류 없음 / 성공 |
| `apps/web` | `npm test` | 23 files, 331 passed |

**NOT_RUN(리뷰 수정):** `npm run api:types:check`(라우터 미mount·OpenAPI 미변경), `npm audit`, 브라우저 E2E, 실제 커뮤니티 actor·모집 어댑터, MariaDB, GitHub Actions CI(push 후 확인).

**NOT_RUN:** `npm audit`, `node scripts/check-agent-config.mjs`, `node scripts/check-feature-progress.mjs`(공통 파일 미변경), MariaDB, 실제 인증 401 경로, 라우터 mount 후 OpenAPI 재생성, 브라우저 E2E, GitHub Actions CI(root 확인 필요). fake 저장소 검증은 MariaDB 증거가 아니다.
