# TASK-OPPORTUNITIES — 장학금·공모전·개인 기회 준비 1차 구현

2026-10-30 KST · 브랜치 `feat/opportunity-firstpass-20261030` · 상태: **review (공통 미연결)**

이 문서는 API-OPP feature 패키지와 프런트 standalone 화면 소스의 실제 구현·검증 상태를 기록한다. 앱 라우터 집계·인증·DB·OpenAPI 스냅샷·프런트 shell 연결은 root/다른 담당 브랜치 소관이며 이 PR에서 수정하지 않았다. 전체 92개 FR 중 어떤 것도 VERIFIED로 주장하지 않는다.

## 1. 근거와 추적

| 구분 | ID | 근거 |
|---|---|---|
| FR | FR-OPP-001(공개 읽기만), FR-OPP-003, FR-OPP-004(P0) | `docs/02_FRD.md` §FR-OPP-001~004, `docs/v1-draft/09_FEATURE_TRACEABILITY.csv` 26~29행 |
| FR 범위 밖 | FR-OPP-001 담당자 쓰기, FR-OPP-002 맞춤 조회, FR-OPP-005 팀 모집 연결, FR-OPP-006 교내 접수·심사 | 아래 §4 |
| API | API-OPP `/opportunities`, `/me/saved-opportunities/**` | `docs/v1-draft/05_DB_API.md`, `docs/v1-draft/13_P0_SERVER_DB_RLS_CONTRACT.md` §5 |
| RBAC | RBAC-OPP; 개인 장학 준비상태 본인만 CRUD | `docs/v1-draft/04_RBAC.md`, `docs/04_POLICY_RBAC.md` §2·§7 |
| 결정 | DEC-013(외부 장학 직접 제출), DFLT-006(자체 신고), DEC-015(FastAPI/React) | `docs/11_DECISION_LOG.md` |
| NFR | NFR-SEC-001/002/005, NFR-DATA-002, NFR-REL-001, NFR-UX-001, NFR-PRIV-002 | `docs/03_NFR.md` |
| TC | TC-V1-OPP-001(공개 읽기 부분), TC-V1-OPP-003, TC-V1-OPP-004, TC-V1-X03(저장/체크/자기 기록 부분), TC-004 | `docs/v1-draft/08_TEST_QA.md`, `docs/08_TEST_QA.md` |

## 2. 변경 파일

- `services/api/app/features/opportunities/`
  - `schemas.py` — Pydantic DTO. `extra="forbid"`로 본문 `user_id` 등 신원 필드 거부. 상태 `interested/preparing/self_reported_submitted/closed`.
  - `repository.py` — `OpportunityCatalog`, `SavedOpportunityStore` Protocol과 레코드. **운영 어댑터 없음.**
  - `service.py` — 순수 서비스: 공개 필터·방어적 재필터, http(s) 외 URL 제거, 원문 확인 필요 표시, 멱등 저장, If-Match revision, 상태 전이표, 자체 신고 정정 이벤트, 체크리스트 CRUD·정렬 충돌·멱등 키.
  - `dependencies.py` — `Principal`, `OpportunityDependencies`. 기본값은 인증·카탈로그·저장소 모두 **503 UNAVAILABLE**(실패 닫힘).
  - `router.py`, `__init__.py` — `create_router(deps)`와 기본 `router` export. 경로는 상대 경로이며 root가 `/api/v1` prefix로 mount.
- `services/api/tests/test_opportunities_support.py`(테스트 전용 메모리 fake), `test_opportunities_service.py`, `test_opportunities_http.py`
- `apps/web/src/features/opportunities/` — `index.tsx`(default 컴포넌트), `api.ts`, `types.ts`, `status.ts`
- 이 문서

## 3. 구현된 계약

| 메서드·경로 (root mount 후 `/api/v1` 접두) | 권한 | 주요 동작·오류 |
|---|---|---|
| `GET /opportunities?kind&q&department&open_only&limit&cursor` | 공개(승인 공개 projection) | `published`만. `department`는 표시 필터일 뿐 권한 아님. 응답 `data={items,next_cursor}` (공통 `SuccessResponse`가 `next_cursor` 필드를 갖지 않으므로 data 내부에 둠) |
| `GET /opportunities/{id}` | 공개 | 비공개/부재 404. 제출 방식·제출처·양식·원문 링크, `platform_receives_submission=false`, `needs_verification` |
| `GET /me/saved-opportunities` | 본인 | 검증된 principal의 행만. 원 공고가 비공개 전환되면 `opportunity=null` |
| `PUT /me/saved-opportunities/{id}` | 본인 | 최초 201, 반복 200 동일 행(본문 무시). 비공개 공고 404 |
| `PATCH /me/saved-opportunities/{id}` | 본인 | `If-Match` 필수(누락·형식 오류 400), revision 불일치·CAS 실패 409, 허용되지 않은 전이 409, `info_only` 공고의 자체 신고 409 |
| `DELETE /me/saved-opportunities/{id}` | 본인 | `If-Match` 필수, 체크 항목 함께 삭제 |
| `POST …/{id}/checks` | 본인 | `Idempotency-Key` 필수. 같은 키·같은 본문은 같은 항목(200), 다른 본문 409. 정렬 중복 409, 항목 50개 초과 409 |
| `PATCH`/`DELETE …/{id}/checks/{check_id}` | 본인(부모 소유권 확인) | `If-Match` 필수. 다른 저장 항목의 체크 404 |

상태 전이: `interested→preparing|closed`, `preparing→interested|self_reported_submitted|closed`, `self_reported_submitted→preparing(정정 이벤트)|closed`, `closed`는 종착(삭제로 초기화). `self_reported_submitted_at`은 서버 시각으로만 기록되며 외부 접수 확인으로 승격되지 않는다. 타인 소유 행은 부재와 구별 없이 404.

프런트는 성공 목업 없이 서버 응답만 표시한다. 변경 후 낙관적 갱신 없이 목록을 서버에서 다시 읽고, "서버가 요청을 처리했습니다" 이상의 저장 완료 표현을 쓰지 않는다. 503은 "서버 연결 준비 중", 401/404/409/400/네트워크 오류, 로딩·빈 상태를 구분한다. 자체 신고 상태 표시는 "제출했다고 직접 기록함"과 "기관 접수·선정 확인이 아님" 안내를 함께 둔다.

## 4. 상태 구분

| 항목 | 상태 | 근거·사유 |
|---|---|---|
| API-OPP feature 서비스·DTO·Protocol·주입형 라우터 | IMPLEMENTED (부분) | FR-OPP-001 읽기, FR-OPP-003 안내, FR-OPP-004 전체 동작 |
| 순수 서비스·HTTP 계약 | TESTED (unit) | 메모리 fake + FastAPI TestClient, 공통 오류 처리기 사용 |
| 실제 인증 의존성 연결 | **BLOCKED** | OPEN-002/003, 공통 auth 담당 브랜치. 기본 503 |
| 실제 DB 저장소(MariaDB 어댑터·migration·UNIQUE/CAS·감사) | **BLOCKED** | 공통 DB 모델 담당, 클라우드 접속정보 없음. Protocol만 제공 |
| 앱 라우터 mount·OpenAPI 스냅샷·프런트 생성 타입 | NOT_RUN (root 통합) | 공통 파일 수정 금지. 현재 `services/api/openapi.json` 불변 |
| 프런트 typecheck/build/브라우저 검증 | NOT_RUN | `apps/web` shell·`src/lib/api.ts`·package 미존재, npm 설치 금지 |
| FR-OPP-001 담당자 공고 쓰기 | BLOCKED | 관리자/담당자 권한·감사 정책 미정, 임의 생성 금지 |
| FR-OPP-002 학과·학년 맞춤 | BLOCKED | 승인된 소속(`academic_memberships`) 공통 원장 필요 |
| FR-OPP-005, FR-OPP-006 | 범위 밖 (P2) | 모집 도메인 연결·교내 심사 정책 별도 태스크 |
| TC-V1-OPP-004 / TC-V1-X03 2계정·DB 영속·재로그인 | NOT_RUN | 실제 인증·DB 연결 후 수행 |

## 5. root 통합 시 연결 방법과 남은 게이트

```python
from app.features.opportunities import OpportunityDependencies, create_router
router.include_router(create_router(OpportunityDependencies(
    current_principal=<공통 인증 의존성 → Principal(user_id)>,
    catalog=<승인 공개 projection 저장소>,
    store=<SavedOpportunityStore 구현>,
)))
```

1. 공통 auth 의존성이 검증된 내부 UUID를 `Principal`로 반환(401은 공통 담당). 본문·쿼리의 신원 값은 사용 금지.
2. DB 어댑터: `(user_id, opportunity_id) UNIQUE`의 `insert_if_absent` 원자성, `compare_and_set*`의 revision 조건부 UPDATE, `delete_with_checks` 트랜잭션, 멱등 키 `(saved_id,key)` UNIQUE + 요청 해시 저장, `append_status_event`의 감사/보존(OPEN-009).
3. CORS는 현재 GET만 허용 — 변경 메서드를 쓰려면 root가 설정을 조정해야 한다.
4. mount 후 OpenAPI 스냅샷 재생성과 프런트 타입 일치 검사, 2계정 E2E(TC-V1-OPP-004).
5. 공개 시드는 관리자 승인 가상(DEMO) 공고만. 실제 학교 데이터 반입 금지.

## 6. 실행한 검증 (services/api, uv 0.13.6 / Python 3.13)

- `uv sync --locked` — 성공
- `uv run --locked ruff check .` — All checks passed
- `uv run --locked ruff format --check .` — 31 files already formatted
- `uv run --locked pytest -q` — 90 passed (기존 24 + 신규 66), 기존 httpx 사용 중단 예정 경고 1건
- `git diff --check` — 결과는 PR 본문에 기록
