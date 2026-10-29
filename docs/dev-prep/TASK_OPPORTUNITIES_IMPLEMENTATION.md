# TASK-OPPORTUNITIES — 장학금·공모전·개인 기회 준비 1차 구현

2026-10-30 KST · 브랜치 `feat/opportunity-firstpass-20261030` · 상태: **review (독립 리뷰 결함 수정 반영, 공통 미연결)**

2차(독립 리뷰 수정): `origin/main`(c00b63a, 신규 `apps/web`·MariaDB 기준 포함)을 리베이스 없이 병합(67da062)한 뒤 아래 §7의 결함을 고쳤다. 새 DB 기준은 팀원 Proxmox VM의 MariaDB 11.4(Tailscale private 3307, 앱 계정 DML 전용·migrator DDL 분리)이지만, 이 작업에서는 DB에 접속·컨테이너 생성·마이그레이션을 **하지 않았다**(Tailscale 오프라인·자격 증명 없음). 모든 검증은 메모리 fake와 단위/HTTP/Vitest 수준이다.

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
- `apps/web/src/features/opportunities/` — `index.tsx`(default 컴포넌트), `api.ts`, `types.ts`, `status.ts`, `api.test.ts`·`index.test.tsx`(Vitest)
- 이 문서

## 3. 구현된 계약

| 메서드·경로 (root mount 후 `/api/v1` 접두) | 권한 | 주요 동작·오류 |
|---|---|---|
| `GET /opportunities?kind&q&department&open_only&limit&cursor` | 공개(승인 공개 projection) | `published`만. `department`는 표시 필터일 뿐 권한 아님. 응답 `data={items,next_cursor}` (공통 `SuccessResponse`가 `next_cursor` 필드를 갖지 않으므로 data 내부에 둠) |
| `GET /opportunities/{id}` | 공개 | 비공개/부재 404. 제출 방식·제출처·양식·원문 링크, `platform_receives_submission=false`, `needs_verification` |
| `GET /me/saved-opportunities` | 본인 | 검증된 principal의 행만. 원 공고가 비공개 전환되면 `opportunity=null` |
| `PUT /me/saved-opportunities/{id}` | 본인 | 최초 201, 반복 200 동일 행(본문 무시). 비공개 공고 404 |
| `PATCH /me/saved-opportunities/{id}` | 본인 | `If-Match` 필수(누락·형식 오류 400), revision 불일치·CAS 실패 409, 허용되지 않은 전이 409, `info_only` 공고의 자체 신고 409. 상태 변경과 상태 이벤트는 한 트랜잭션(이벤트 실패 시 500 + 상태 불변) |
| `DELETE /me/saved-opportunities/{id}` | 본인 | `If-Match` 필수, 체크 항목 함께 삭제(멱등 키 기록은 tombstone으로 보존) |
| `POST …/{id}/checks` | 본인 | `Idempotency-Key` 필수. 키 범위 = (검증된 user_id, opportunity_id, 작업 경로, 키). 같은 키·같은 본문은 같은 항목(200), 다른 본문 409, **생성 항목이 삭제됐거나 저장 행이 삭제 후 재생성된 뒤의 재전송도 409**(새 ID로 부활 금지). 정렬 중복 409, 항목 50개 초과 409 |
| `PATCH`/`DELETE …/{id}/checks/{check_id}` | 본인(부모 소유권 확인) | `If-Match` 필수. 다른 저장 항목의 체크 404 |

상태 전이: `interested→preparing|closed`, `preparing→interested|self_reported_submitted|closed`, `self_reported_submitted→preparing(정정 이벤트)|closed`, `closed`는 종착(삭제로 초기화). **`closed` 종착과 "삭제 = 유일한 초기화 경로"는 학교 정책이 아니라 시연용 설계 가정이다.** 학교의 재신청·추가 모집 정책이 승인되면 전이표를 다시 정한다(사람 승인 게이트).

`If-Match`(RFC 9110 strong 비교): 1~999999999의 ASCII 양의 정수 `7` 또는 정확한 strong 태그 `"7"`만 허용한다. `W/"7"`(weak), `"1", "2"`(목록), `*`, `""1`·`1""`·`"1` 같은 비정상 따옴표, 선행 0, `+1`, 아랍·전각 등 비 ASCII 숫자는 400 VALIDATION. 저장소 계약상 불일치는 RFC의 412 대신 공통 오류 계약의 409 CONFLICT를 유지한다.

출처(`source_kind`): 공통 계약 `OFFICIAL_PUBLIC|DEMO|USER_DEMO`(`docs/v1-draft/05_DB_API.md`) 중 공개 카탈로그는 `OFFICIAL_PUBLIC`, `DEMO`만 노출한다. 1차 구현의 `PUBLIC_SOURCE`는 OpenAPI 스냅샷·라우터 mount 전이라 외부 계약으로 공개된 적이 없어 `OFFICIAL_PUBLIC`으로 이름을 바꿨다. 어댑터는 `repository.source_kind_from_storage`로 매핑한다.

| 저장 값 | API 값 | 비고 |
|---|---|---|
| `OFFICIAL_PUBLIC`, `official_public`(`docs/research/07_DATA_PROVENANCE_AND_SEEDS.md` 제안) | `OFFICIAL_PUBLIC` | `checked_at`·안전한 원문 URL 없으면 `needs_verification=true` |
| `DEMO`, `synthetic_demo`(조사 문서 제안) | `DEMO` | 항상 `needs_verification=true`, 화면에 "DEMO 가상 공고" |
| `USER_DEMO`, 그 외 | 거부(`ValueError`) | 관리자 승인 카탈로그에 사용자 생성 시연물 불가 |

`self_reported_submitted_at`은 서버 시각으로만 기록되며 외부 접수 확인으로 승격되지 않는다. 타인 소유 행은 부재와 구별 없이 404.

프런트 경로는 공유 `requestData`의 기본 base(`/api/v1`)에 상대적이다(`api.ts`의 `BASE=''`). 체크 항목 추가는 **입력 의도마다 키 1개**: 실패하면 입력 텍스트와 키·본문(`sort_order` 포함)을 페이지 상태에 보존하고 버튼이 "다시 시도"로 바뀌며 같은 키·같은 본문으로 재전송한다. 텍스트를 바꾸면 새 의도로 보고 새 키를 만든다. 성공 시에만 입력을 비운다. 프런트는 성공 목업 없이 서버 응답만 표시한다. 변경 후 낙관적 갱신 없이 목록을 서버에서 다시 읽고, "서버가 요청을 처리했습니다" 이상의 저장 완료 표현을 쓰지 않는다. 503은 "서버 연결 준비 중", 401/404/409/400/네트워크 오류, 로딩·빈 상태를 구분한다. 자체 신고 상태 표시는 "제출했다고 직접 기록함"과 "기관 접수·선정 확인이 아님" 안내를 함께 둔다.

## 4. 상태 구분

| 항목 | 상태 | 근거·사유 |
|---|---|---|
| API-OPP feature 서비스·DTO·Protocol·주입형 라우터 | IMPLEMENTED (부분) | FR-OPP-001 읽기, FR-OPP-003 안내, FR-OPP-004 전체 동작 |
| 순수 서비스·HTTP 계약 | TESTED (unit) | 메모리 fake + FastAPI TestClient, 공통 오류 처리기 사용 |
| 멱등 tombstone·키 범위·동시 같은 키·UNIQUE→409·CAS+이벤트 원자성 | TESTED (fake 계약) | 테스트 전용 `FakeStore`가 문서화된 트랜잭션 계약을 흉내 냄. **실제 MariaDB 트랜잭션·락은 NOT_RUN** |
| 프런트 API URL·UI 상태·재시도 | TESTED (Vitest, jsdom) | 실제 공유 `requestData` + fetch stub. 브라우저 E2E는 NOT_RUN |
| 실제 인증 의존성 연결 | **BLOCKED** | OPEN-002/003, 공통 auth 담당 브랜치. 기본 503. 교직원 범위 활성화도 차단 유지 |
| 실제 DB 저장소(MariaDB 11.4 어댑터·migration·UNIQUE/CAS·감사) | **BLOCKED / NOT_RUN DB** | 공통 DB·migration 담당. Tailscale 오프라인·자격 증명 없음. Protocol과 fake 계약만 제공 |
| 앱 라우터 mount·OpenAPI 스냅샷·프런트 생성 타입 | NOT_RUN (root 통합) | 공통 파일 수정 금지. `services/api/openapi.json` 불변이며 `api:types:check`는 기존 스냅샷 기준으로만 통과 |
| 프런트 shell 연결 | NOT_RUN (root 통합) | `App.tsx`·`navigation.ts`는 공통 파일. 현재 `/app/opportunities`는 shell의 준비 중 화면이고 이 기능 모듈은 번들에 포함되지 않는다(typecheck·Vitest로만 검증) |
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
2. DB 어댑터(UoW 계약, `repository.py` 모듈 docstring):
   - `insert_if_absent`: `(user_id, opportunity_id) UNIQUE` 원자 삽입.
   - `compare_and_set(record, expected_revision, event)`: **한 트랜잭션**에서 `UPDATE … WHERE revision=?`와 상태 이벤트 INSERT. 이벤트 INSERT 실패 시 ROLLBACK 후 예외 전파(→500, 상태 불변). 별도 `append_status_event` 호출은 제거했다.
   - `insert_check(record, scope, request_hash)`: **한 트랜잭션**에서 멱등 키 행(UNIQUE `(user_id, opportunity_id, operation, key)`)과 체크 행 삽입. 키 충돌 시 아무것도 쓰지 않고 기존 항목 반환. `(saved_id, sort_order)` UNIQUE 위반은 `StoreConflict`(→409).
   - `delete_check`/`delete_with_checks`: 멱등 키 행을 지우지 않는다(tombstone, `check=None`). 키 보존 기간·정리 작업은 OPEN-009/OPEN-R14 보존 정책 결정 후 정한다(사람 승인 게이트).
   - 상태 이벤트의 감사/보존(OPEN-009).
3. CORS는 현재 GET만 허용 — 변경 메서드를 쓰려면 root가 설정을 조정해야 한다.
4. mount 후 OpenAPI 스냅샷 재생성과 프런트 타입 일치 검사, 2계정 E2E(TC-V1-OPP-004).
5. 공개 시드는 관리자 승인 가상(DEMO) 공고만. 실제 학교 데이터 반입 금지.

## 6. 검증 구분 (2차, main 병합 후 로컬 Windows)

**실제 실행함** (uv는 `C:/DIT CSW/ditNow-python-tools/Scripts/uv.exe`):

| 위치 | 명령 | 결과 |
|---|---|---|
| `services/api` | `uv sync --locked` | 성공 |
| `services/api` | `uv run --locked ruff check .` | All checks passed |
| `services/api` | `uv run --locked ruff format --check .` | 37 files already formatted |
| `services/api` | `uv run --locked pytest -q` | 149 passed, 기존 httpx 사용 중단 경고 1건 |
| `apps/web` | `npm ci` | 성공, 0 vulnerabilities |
| `apps/web` | `npm run api:types:check` | 기존 공개 스냅샷과 일치(이 기능은 스냅샷에 없음) |
| `apps/web` | `npm run typecheck` | 오류 없음 |
| `apps/web` | `npm test` | 4 files, 47 passed(이 기능 신규 2 files) |
| `apps/web` | `npm run build` | 성공(이 기능은 shell 미연결이라 번들 미포함) |
| 회귀 확인 | `BASE='/api/v1'`로 임시 복원 후 `api.test.ts` | 10건 실패(`/api/v1/api/v1/…` 재현), 복원 후 통과 |

**미검증(NOT_RUN):** MariaDB 11.4 실제 트랜잭션·락·UNIQUE 동작, migration, 실제 인증 401 경로, 앱 라우터 mount 후 OpenAPI 재생성, 브라우저 E2E, 2계정 TC-V1-OPP-004/TC-V1-X03, GitHub Actions CI(권한 있는 조회 도구로 root 확인 필요).

**사람 승인 게이트:** 공통 auth·교직원 범위 활성화(차단 유지), DB 어댑터·migration 소유자 지정과 실행, 앱 라우터·shell 연결, CORS 변경 메서드 허용, 멱등 키·상태 이벤트 보존 기간(OPEN-009/R14), `closed` 종착 정책의 학교 기준 확정, merge·배포.

## 7. 독립 리뷰 결함과 조치 (2차)

| # | 결함 | 조치 | 증거(테스트) |
|---|---|---|---|
| 1 | 공유 `requestData`가 `/api/v1`을 붙이는데 `api.ts`도 붙여 `/api/v1/api/v1/…` | `BASE=''` | `api.test.ts`: 9개 호출 최종 URL 1회 접두, 절대 base 설정 |
| 2 | 체크 생성→삭제 후 같은 키·본문 재전송 시 새 ID로 부활 | 키 tombstone 보존, 키 범위(actor·부모·작업) 명시, 재전송 409, 동시 같은 키는 승자 재생, UNIQUE 위반 `StoreConflict`→409 | `test_replay_after_delete_*`, `test_replay_after_saved_reset_*`, `test_idempotency_key_is_scoped_*`, `test_*race*`, `test_check_replay_after_delete_is_conflict_not_new_item` |
| 3 | UI가 시도마다 새 키를 만들고 실패 전 입력을 지움 | 의도별 키·본문을 페이지 상태에 보존, 실패 시 입력 유지·"다시 시도", 성공 시에만 비움 | `index.test.tsx` checklist 4건 |
| 4 | `parse_if_match`가 `W/"1"`, `""1`, `1""`를 허용 | ASCII 정수 또는 정확한 strong 태그만 | `test_if_match_required_and_validated`(21 케이스), `test_parse_if_match_*` |
| 5 | CAS 후 별도 이벤트 기록 — 감사 실패 시 상태만 바뀜 | `compare_and_set(record, rev, event)` 단일 UoW, 실패 시 롤백 | `test_status_event_failure_rolls_back_state`, `test_status_event_failure_returns_500_and_keeps_state` |
| 6 | `PUBLIC_SOURCE`가 공통 `OFFICIAL_PUBLIC` 계약과 불일치 | 이름 변경 + 어댑터 매핑표 | `test_source_kind_*` |
| 7 | `closed` 종착/삭제 초기화의 근거 불명 | 시연 설계 가정으로 명시(§3, `service.py` 주석) | 문서 |
| 8 | (테스트 중 발견) 공유 client는 네트워크 오류를 `ApiError(status 0)`로 주므로 네트워크 안내가 표시되지 않음 | `describeError`가 `NETWORK`/`CANCELLED` 인식 | `index.test.tsx` 네트워크 재시도 |
| UI | 로딩/503/401/오류 재시도 테스트 없음 | 추가 | `index.test.tsx` states 4건 |
