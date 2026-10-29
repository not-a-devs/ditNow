# TASK-CAMPUS 학과·학년 채팅 · 공식 공지 · 학사 일정 1차 구현

2026-10-30 KST · 브랜치 `feat/campus-communication-firstpass-20261030` · 상태 `review` (공통 auth/DB 미연결). 같은 날 `origin/main`(apps/web 공통 기반 포함)을 병합하고 독립 리뷰 결함을 수정했다(§9).

전체 92개 FR 가운데 독립적으로 구현할 수 있는 학과 소통 부분만 담당한다. 이 문서의 TESTED는 아래에 적은 단위·HTTP 테스트(테스트 전용 메모리 fake 사용)에 한정되며, 어떤 FR도 VERIFIED가 아니다.

## 1. 대상 요구사항과 상태

| FR | 추적표 TC | 우선순위 | 이 PR 범위 | 상태 |
|---|---|---|---|---|
| FR-DEPT-001 학과 전체 채팅 | TC-V1-DEPT-001, TC-007/008 | P0 | 소속 학과 기본 채널 목록, 다른 학과 거부 | IMPLEMENTED(부분) / TESTED(unit) |
| FR-DEPT-002 학년별 채팅 | TC-V1-DEPT-002 | P0 | 같은 학과 다른 학년 거부, 학년 미지정 소속은 학년 채널 거부 | IMPLEMENTED(부분) / TESTED(unit) |
| FR-DEPT-005 메시지 전송·조회 | TC-V1-DEPT-005 | P0 | 텍스트 전송·cursor 조회·`client_nonce` 중복 방지. 파일·삭제·검색 없음 | IMPLEMENTED(부분) / TESTED(unit) |
| FR-NOT-001 공식 공지 CRUD | TC-V1-NOT-001, TC-005 | P0 | 학교/학과/학과·학년 대상 초안→게시→개정→보관, 범위 권한, 낙관적 동시성 | IMPLEMENTED(부분) / TESTED(unit) |
| FR-NOT-002 자동 채팅 전달 카드 | TC-V1-NOT-002, TC-006, TC-V1-X01 | P0 | 원본 1건 + 대상 기본 채널 참조 카드, 3회 처리해도 카드 1건, 카드가 원본 최신판을 표시 | IMPLEMENTED(부분) / TESTED(unit) |
| FR-ACA-001 학사 일정·학기 조회 | TC-V1-ACA-001 | P2(DEMO_ONLY) | 학기 목록·학기별 일정 조회(기간 필터), `source_kind` 표시. 개인 시간표 없음 | IMPLEMENTED(부분) / TESTED(unit) |

관련 NFR: NFR-SEC-001~003(서버 권한·입력 검증), NFR-REL-002(outbox 멱등성 — 서비스 수준만), NFR-DATA-001(단일 원본+참조 카드), NFR-UX-001(로딩/빈/오류/권한 상태), NFR-PRIV-001(채팅 응답은 작성자 UUID·`is_mine`만; 실명/프로필은 미포함). 정책: RBAC-DEPT, RBAC-NOT, RBAC-ACA, DEC-006/008, DFLT-002/004, OPEN-004(수정 시 재전달 없음).

범위 밖: 분반·개인 대상 공지, 첨부·검색·읽음 통계(FR-NOT-003~005), 자유/공식 채널(FR-DEPT-003/004), 메시지 파일·삭제·검색, 알림 전송, 개인 시간표, FR-ACA-002~011.

## 2. 구현 위치

- 백엔드 `services/api/app/features/campus/`
  - `domain.py` 저장소와 무관한 값 객체(Audience, CampusActor, Channel, ChatMessage, Notice, AcademicTerm/Event).
  - `policy.py` 순수 권한 규칙: 채널 접근, 공지 작성 범위(정확 일치), 공지 열람, 대상→전달 채널 계산(DFLT-004: 학교 전체 공지는 채팅 복제 없음).
  - `repositories.py` `ActorResolver`와 저장소 Protocol. 각 메서드에 실제 어댑터가 지켜야 할 유일 제약을 주석으로 명시.
  - `services.py` `ChatService`, `NoticeService`(publish/deliver 분리, deliver 재실행 멱등), `AcademicService`. 모든 메서드가 권한을 다시 검사한다.
  - `schemas.py` Pydantic DTO(`extra="forbid"`). 응답 봉투는 `app/schemas/common.py`.
  - `router.py` `build_campus_router(provider)`와 기본 `router`. 경로는 접두사 없이 정의되며 root가 `/api/v1`에 장착한다.
- 테스트 `services/api/tests/test_campus_support.py`(테스트 전용 fake), `test_campus_policy.py`, `test_campus_services.py`, `test_campus_http.py`.
- 프런트 `apps/web/src/features/campus/` — `index.tsx`(default `CampusPage`), `ChatPanel`, `NoticePanel`(읽기 전용), `AcademicPanel`, `StatusView`, `api.ts`, `model.ts`, `types.ts`.

## 3. API 계약 (장착 후 `/api/v1` 기준)

| 메서드·경로 | 권한 | 성공 | 주요 실패 |
|---|---|---|---|
| GET `/departments/{id}/channels` | 해당 학과 현재 소속 | 학과 전체 + 본인 학년 채널만 | 401, 403, 503 |
| GET `/channels/{id}/messages?before&limit` | 채널 접근 | 최신순, `next_before` cursor, 카드에는 원본 최신 제목·개정 | 400, 401, 403, 404 |
| POST `/channels/{id}/messages` `{body, client_nonce}` | 채널 접근 | 201 신규 / 200 `replayed=true` | 400, 403, 409(같은 nonce 다른 내용) |
| GET `/notices?limit` | 인증 | 본인 대상의 게시·보관 공지만 | 401 |
| POST `/notices` `{audience,title,body}` | 승인된 작성 범위 | 201 초안, `resource_version=revision` | 400, 403 |
| GET `/notices/{id}` | 작성 범위 또는 게시 대상 | 원본 | 403(범위 밖), 404(없음/타인 초안) |
| PATCH `/notices/{id}` `{title,body,expected_revision}` | 작성 범위 | revision+1 | 409(개정 충돌/보관됨/동시 상태 변경) |
| POST `/notices/{id}/publish` `{expected_revision}` | 작성 범위 | 게시 + `delivery{channel_ids,created_count,pending_target_count}` | 400(본문 누락), 409(보관됨·개정 불일치) |
| POST `/notices/{id}/archive` `{expected_revision}` | 작성 범위 | 보관(같은 개정 재호출 멱등) | 400, 403/404, 409(개정 불일치) |
| GET `/academic/terms`, `/academic/terms/{id}/events?from&to` | 인증 | `source_kind`·`source_url`·`checked_at`(학기·일정 모두) | 400(기간 역전·366일 초과), 404 |

순서: 런타임 미주입→503 `UNAVAILABLE`, 인증 실패→401, 이후 입력 검증(400)과 권한(403/404). 잘못된 JSON 문법은 FastAPI가 의존성 이전에 400으로 처리한다. 범위 밖 게시 공지는 TC-V1-X01에 맞춰 403이며, 이 때문에 존재 여부가 추론될 수 있다(정책 확정 필요).

## 4. 설계 가정 (정책 확정 아님)

- 작성 권한은 `CampusActor.notice_author_scopes`의 **정확 일치**만 허용한다. 학과 범위가 학년 범위를 암묵적으로 포함하지 않는다. 어떤 역할(교수/조교/학과 대표)이 어떤 범위를 받는지는 공통 auth 담당자와 OPEN-R11 결정 사항이며 이 PR은 역할명을 판단하지 않는다.
- 학년 정보가 없는 소속(예: 교직원)은 학과 전체 채널만 접근한다. 더 넓은 접근은 정책 승인 전 거부한다.
- **위 두 규칙은 학교 정책이 아니라 이 PR의 보수적 가정이다.** 교수·조교에게 어떤 정확 범위를 부여할지, 학년 없는 교직원이 학년 채널에 참여할지는 공통 auth 담당자와 사람 승인(OPEN-R11) 전까지 **BLOCKED**이며, 이 PR은 역할명→범위 매핑이나 교직원 학년 채널 접근을 활성화하지 않는다. 승인 없이 권한을 넓히는 변경은 하지 않는다.
- 공지 게시·보관은 작성자가 마지막으로 본 `expected_revision`에만 적용한다. 그 사이 다른 편집자가 개정하면 409이며 의도하지 않은 판이 게시·보관되지 않는다. 상태 전이는 개정 번호를 올리지 않는다.
- 학사 자료 출처: `OFFICIAL_PUBLIC`은 http(s) 절대 URL(자격증명·공백·제어문자 없음, 2048자 이하)과 시간대가 있는 `checked_at`이 모두 있을 때만 그대로 응답한다. 하나라도 없거나 위험하면 서버가 `UNKNOWN`(출처 미확인)으로 낮추고 링크·확인시각을 지운다. `DEMO`(가상)와 `UNKNOWN`(레거시·출처 불명)은 서로 다르며 둘 다 링크를 갖지 않는다. 프런트도 같은 허용 목록(`citationOf`)으로 한 번 더 걸러 서버 실수에도 `javascript:` 링크가 만들어지지 않는다.
- 학년 입력은 1~6만 받는 형식 검증이다. 실제 접근은 서버가 조회한 소속으로 판단한다.
- 게시 후 대상(audience)은 바꿀 수 없다(입력 모델에 없음). 개정은 카드를 새로 만들지 않고 카드가 원본 최신판을 읽는다(OPEN-004 기본값).
- 대상 채널이 없으면 공지는 게시 상태로 두고 `pending_target_count`로 보고한다. 성공 카드를 꾸며내지 않는다.

## 5. 실제 검증 (2026-10-30, Windows, Python 3.13, `C:/DIT CSW/ditNow-python-tools/Scripts/uv.exe`, origin/main 병합 후)

`services/api`에서 실행(실제 실행·결과):
- `uv sync --locked` — 성공.
- `uv run --locked ruff check .` — All checks passed.
- `uv run --locked ruff format --check .` — 39 files already formatted.
- `uv run --locked pytest -q` — 148 passed(이 중 campus 3개 파일 111). 경고 1건은 기존 Starlette TestClient/httpx 사용 중단 예정 경고.

`apps/web`에서 실행(실제 실행·결과, Node 22 로컬):
- `npm ci` — 152 packages, 0 vulnerabilities.
- `npm run api:types:check` — 생성 타입이 공개 스냅샷과 일치. campus 라우터는 아직 공용 앱에 장착되지 않아 스냅샷에 campus 경로가 없고, `types.ts`는 손으로 맞춘 거울 타입이다.
- `npm run typecheck` — 오류 없음.
- `npm test` — 4 files, 85 passed(이 중 campus `api.test.ts` 45 + `index.test.tsx` 13).
- `npm run build` — 성공. 단, 현재 `App.tsx`가 campus 화면을 import하지 않아 번들에는 campus 코드가 포함되지 않는다(타입검사·Vitest로만 검증).
- 회귀 확인: `api.ts`의 `BASE`를 일시적으로 `/api/v1`로 되돌리면 campus 테스트 16건이 `/api/v1/api/v1/...`로 실패함을 실제로 확인한 뒤 원복했다.

테스트가 증명하는 것: 미주입 라우터 11개 경로 전부 503, 미인증 11개 경로 전부 401이며 기록이 생기지 않음; 다른 학과·다른 학년 채널 403; nonce 재전송 1건 유지·다른 내용 재사용 409; 제어문자·RTL override·길이·추가 필드(`author_id` 위조) 400이며 입력값이 응답에 반사되지 않음; 학생/타 학과 조교의 공지 작성 403; 타인 초안 404; 게시 3회 처리 시 카드 1건; 개정 후 카드가 v2 표시; 다른 채널 카드 없음; 학교 전체 공지 채팅 복제 없음; 개정 충돌·보관 후 게시/개정 409; 학사 정렬·기간 필터·검증; 공용 앱 OpenAPI에 campus 경로가 아직 없음. 추가로(§9): 게시·보관의 `expected_revision` 누락 400·불일치 409와 부수효과 없음, 읽기와 CAS 사이 다른 편집자의 개정/보관이 끼어드는 경합(fake의 `interleave` 훅)에서 409이며 보관 상태가 개정으로 덮이지 않음, 같은 개정 동시 게시는 카드 1건으로 멱등; `OFFICIAL_PUBLIC` 학사 일정·학기의 `javascript:`/상대·자격증명 URL/`checked_at` 누락·naive 시각은 `UNKNOWN`으로 응답; 프런트 최종 URL이 `/api/v1` 접두사 1회, 로딩·503·401·403·네트워크 오류·재시도 UI, 불명확 실패 후 같은 본문은 같은 nonce·본문 수정·409 후에는 새 nonce, 카드→원본 열 때마다 최신 원본 재조회.

## 6. 미검증·차단 (정확한 구분)

| 항목 | 상태 | 이유/연결 조건 |
|---|---|---|
| 공통 앱 장착(`app/api/v1/router.py` 또는 factory) | BLOCKED | 공통 파일 수정 금지. root가 `from app.features.campus import router`(503 기본) 또는 `build_campus_router(provider)`로 장착 |
| 인증(`ActorResolver`) | BLOCKED(auth) | 공통 인증 공급자 미정. 세션 검증 후 **현재** 소속·`role_assignments`를 DB에서 다시 읽어 `CampusActor`를 만들어야 함 |
| DB 영속성(MariaDB 어댑터·마이그레이션) | BLOCKED(DB) / NOT_RUN | 대상은 팀원 Proxmox VM의 MariaDB 11.4(Tailscale private, 3307), 앱 계정 DML 전용·migrator 계정 DDL 분리. 이 작업에서는 접속·로컬 DB 컨테이너·마이그레이션을 **시도하지 않았다**. 필요한 제약: `channels` UNIQUE(department_id, grade) 기본 채널, `channel_messages` UNIQUE(channel_id, author_id, client_nonce)와 UNIQUE(channel_id, reference_notice_id), notices는 `UPDATE … WHERE id=? AND revision=? AND status=?` 단일 조건부 갱신(내용 개정은 상태 컬럼을 쓰지 않음), 게시 전이와 outbox 기록의 단일 트랜잭션. CAS는 테스트 fake로만 검증했다 |
| 교수·조교 정확 범위, 학년 없는 교직원의 학년 채널 | BLOCKED(auth·사람 승인) | §4 가정. 공통 auth 담당자 승인 전 활성화하지 않음 |
| outbox 테이블·재시도 워커 | NOT_IMPLEMENTED | `NoticeService.deliver`가 소비자 계약(멱등)만 제공. 현재는 publish 요청 안에서 동기 호출 |
| 실시간 채팅(WebSocket/SSE) | NOT_IMPLEMENTED | 화면에 "실시간 수신 미연결" 표시와 수동 새로고침만 제공. TC-007 실시간 수신은 NOT_RUN |
| 요청 제한·감사 로그 | NOT_IMPLEMENTED | NFR-SEC 요청 제한, 공지 감사 기록은 공통 미들웨어/감사 원장 필요 |
| 프런트 타입검사·Vitest·빌드 | TESTED(unit) | §5. jsdom + fetch stub이며 실제 서버·브라우저 아님 |
| 프런트 shell 장착(`App.tsx` 라우트)·실제 브라우저 | NOT_RUN | `App.tsx`·`navigation.ts`는 공통 소유. root가 `features/campus`의 default `CampusPage`를 학과 메뉴에 연결하고 세션 소속 학과를 넘겨야 함 |
| GitHub Actions CI | 미확인 | 이 환경에 CI 조회 도구 사용을 하지 않았다. root가 PR HEAD의 web-ci·python-api-ci 결과를 확인 |
| 2계정·DB 영속·390/1280 화면·E2E | NOT_RUN | 위 차단 해소 후 TC-V1-DEPT-001/002/005, TC-V1-NOT-001/002, TC-V1-X01로 실행 |

## 7. 프런트 통합 메모

- `index.tsx`의 `CampusPage`는 `departmentId`를 shell(인증 세션)에서 받는다. 없으면 연결 준비 상태만 보여 준다.
- `api.ts`는 공유 `../../lib/api`의 `requestData`를 쓴다. 공유 클라이언트가 `VITE_API_BASE_URL`(기본 `/api/v1`)을 붙이므로 campus 경로는 접두사 없이(`BASE = ""`) 넘긴다. 공통 lib는 수정하지 않았다.
- 503은 "서버 연결 준비 중"으로 표시하며 성공 목업을 보여 주지 않는다. 전송한 메시지는 서버 응답으로 받은 레코드만 목록에 추가하며 DB 영속 확인 전 "저장 완료" 문구를 쓰지 않는다.
- 전송 nonce는 **의도 단위**다: (다듬은 본문, nonce) 쌍을 보존하고 같은 본문 재시도만 같은 nonce를 쓴다. 본문을 고치면 새 nonce이며, 불명확 실패(네트워크·타임아웃·5xx·잘못된 응답) 뒤 본문을 고치면 "이전 메시지가 이미 전송되었을 수 있음"을 안내한다. 409(같은 nonce 다른 내용)면 쌍을 버리고 새 nonce를 쓴다.
- 공지 작성·개정 UI는 역할 판별 계층이 생긴 뒤 추가한다(현재 읽기 전용). `types.ts`는 OpenAPI 생성 타입으로 교체 대상이다.

## 8. 다음 실행 가능 태스크

1. root: 공통 auth `ActorResolver`와 MariaDB 어댑터 연결 후 `build_campus_router` 장착, OpenAPI 스냅샷·프런트 타입 재생성.
2. DB 담당: 위 유일 제약을 포함한 마이그레이션, notice outbox 테이블과 재시도 소비자.
3. 통합 후 2계정 E2E(TC-V1-X01) 및 실시간 전송 방식 결정.
4. 사람 승인: 교수·조교 공지 범위와 학년 없는 교직원의 학년 채널 정책(OPEN-R11) — 승인 전 활성화 금지.

## 9. 독립 리뷰 결함 조치 (2026-10-30)

| # | 결함 | 조치 | 증거(테스트) | 남은 한계 |
|---|---|---|---|---|
| 1 | 프런트 `BASE='/api/v1'` + 공유 `requestData` 기본 접두사 → `/api/v1/api/v1/...` | `BASE = ""` | `api.test.ts` 실제 공유 클라이언트+fetch stub 최종 URL 8개 경로·절대 base·POST 본문·ID 인코딩; 되돌리면 16건 실패 확인 | shell 미장착으로 실제 브라우저 요청은 NOT_RUN |
| 2 | `OFFICIAL_PUBLIC` 학사 일정이 `javascript:` URL·`checked_at` 없음으로 응답·링크 가능 | 서버 `cited()`가 학기·일정 모두 정규화(공식은 http(s)+aware `checked_at` 필수, 아니면 `UNKNOWN`), `SourceKind.UNKNOWN` 추가, `checked_at`을 aware datetime으로, 비공식은 링크 제거. 프런트 `safeSourceUrl`/`citationOf` 허용 목록 | `test_safe_source_url_*`, `test_uncited_official_record_is_downgraded_to_unknown`, `test_official_event_without_safe_citation_is_served_as_unknown`(HTTP 재현), `index.test.tsx` 학사 출처 | 실제 공개 학사 자료 적재·검수 절차 없음 |
| 3 | publish/archive에 `expected_revision` 없음 → 동시 개정 후 의도치 않은 게시/보관; 개정 저장이 동시 보관을 덮을 수 있음 | 두 요청 본문 `{expected_revision}` 필수, 저장소 `transition`·`save_revision`이 revision+status 조건부 갱신, 개정은 상태를 쓰지 않음 | `test_publish_and_archive_reject_stale_revision_without_side_effects`, `test_revision_committed_between_read_and_*`, `test_concurrent_archive_is_not_overwritten_by_revise`, `test_concurrent_publish_of_same_revision_is_idempotent`, HTTP `test_transition_requires_expected_revision`·`test_publish_of_stale_revision_is_409_and_releases_nothing` | 실제 MariaDB 조건부 UPDATE는 NOT_RUN(fake만) |
| 4 | ChatPanel이 실패 후 본문을 고쳐도 같은 nonce 사용 → 409 또는 수정 내용 유실 | 의도별 (본문, nonce) 쌍, 바뀐 본문은 새 nonce, 409 후 새 nonce, 불명확 실패 안내 | `api.test.ts` send intents, `index.test.tsx` chat sending 5건 | 실시간 수신 없음 |
| 5 | 교수·조교 정확 범위/학년 없는 교직원 규칙이 학교 정책처럼 보임 | §4·§6에 가정·BLOCKED(auth·사람 승인)로 명시, `policy.can_author` 주석. 권한 확대 없음 | 기존 정책 테스트 유지 | 정책 미확정 |
| 6 | 출처·공지 캐시·학과 경계 회귀 | 카드가 보관 상태를 반영, 학년 이탈 시 403, 카드→원본은 열 때마다 재조회(목록이 낡아도 최신 원본 표시), 읽을 수 없는 카드는 내용 추측 없이 숨김 | `test_card_reflects_archive_and_stays_inside_audience`, `index.test.tsx` 공지 카드 2건 | — |

완료 주장하지 않는 것: 실시간 채팅, outbox 테이블·재시도 워커, DB 영속성·마이그레이션, 공통 auth 연결, 공용 앱/웹 shell 장착, CI 결과.
