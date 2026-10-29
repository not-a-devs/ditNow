# TASK-CAMPUS 학과·학년 채팅 · 공식 공지 · 학사 일정 1차 구현

2026-10-30 KST · 브랜치 `feat/campus-communication-firstpass-20261030` · 상태 `review` (공통 auth/DB 미연결).

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
| PATCH `/notices/{id}` `{title,body,expected_revision}` | 작성 범위 | revision+1 | 409(개정 충돌/보관됨) |
| POST `/notices/{id}/publish` | 작성 범위 | 게시 + `delivery{channel_ids,created_count,pending_target_count}` | 409(보관됨) |
| POST `/notices/{id}/archive` | 작성 범위 | 보관(재호출 멱등) | 403/404 |
| GET `/academic/terms`, `/academic/terms/{id}/events?from&to` | 인증 | `source_kind` 포함 | 400(기간 역전·366일 초과), 404 |

순서: 런타임 미주입→503 `UNAVAILABLE`, 인증 실패→401, 이후 입력 검증(400)과 권한(403/404). 잘못된 JSON 문법은 FastAPI가 의존성 이전에 400으로 처리한다. 범위 밖 게시 공지는 TC-V1-X01에 맞춰 403이며, 이 때문에 존재 여부가 추론될 수 있다(정책 확정 필요).

## 4. 설계 가정 (정책 확정 아님)

- 작성 권한은 `CampusActor.notice_author_scopes`의 **정확 일치**만 허용한다. 학과 범위가 학년 범위를 암묵적으로 포함하지 않는다. 어떤 역할(교수/조교/학과 대표)이 어떤 범위를 받는지는 공통 auth 담당자와 OPEN-R11 결정 사항이며 이 PR은 역할명을 판단하지 않는다.
- 학년 정보가 없는 소속(예: 교직원)은 학과 전체 채널만 접근한다. 더 넓은 접근은 정책 승인 전 거부한다.
- 학년 입력은 1~6만 받는 형식 검증이다. 실제 접근은 서버가 조회한 소속으로 판단한다.
- 게시 후 대상(audience)은 바꿀 수 없다(입력 모델에 없음). 개정은 카드를 새로 만들지 않고 카드가 원본 최신판을 읽는다(OPEN-004 기본값).
- 대상 채널이 없으면 공지는 게시 상태로 두고 `pending_target_count`로 보고한다. 성공 카드를 꾸며내지 않는다.

## 5. 실제 검증 (2026-10-30, Windows, Python 3.13, `C:/DIT CSW/ditNow-python-tools/Scripts/uv.exe`)

`services/api`에서 실행:
- `uv sync --locked` — 성공.
- `uv run --locked ruff check .` — All checks passed.
- `uv run --locked ruff format --check .` — 33 files already formatted.
- `uv run --locked pytest -q` — 95 passed(기존 24 + campus 신규 71). 경고 1건은 기존 Starlette TestClient/httpx 사용 중단 예정 경고.

테스트가 증명하는 것: 미주입 라우터 11개 경로 전부 503, 미인증 11개 경로 전부 401이며 기록이 생기지 않음; 다른 학과·다른 학년 채널 403; nonce 재전송 1건 유지·다른 내용 재사용 409; 제어문자·RTL override·길이·추가 필드(`author_id` 위조) 400이며 입력값이 응답에 반사되지 않음; 학생/타 학과 조교의 공지 작성 403; 타인 초안 404; 게시 3회 처리 시 카드 1건; 개정 후 카드가 v2 표시; 다른 채널 카드 없음; 학교 전체 공지 채팅 복제 없음; 개정 충돌·보관 후 게시/개정 409; 학사 정렬·기간 필터·검증; 공용 앱 OpenAPI에 campus 경로가 아직 없음.

## 6. 미검증·차단 (정확한 구분)

| 항목 | 상태 | 이유/연결 조건 |
|---|---|---|
| 공통 앱 장착(`app/api/v1/router.py` 또는 factory) | BLOCKED | 공통 파일 수정 금지. root가 `from app.features.campus import router`(503 기본) 또는 `build_campus_router(provider)`로 장착 |
| 인증(`ActorResolver`) | BLOCKED(auth) | 공통 인증 공급자 미정. 세션 검증 후 **현재** 소속·`role_assignments`를 DB에서 다시 읽어 `CampusActor`를 만들어야 함 |
| DB 영속성(MariaDB 어댑터·마이그레이션) | BLOCKED(DB) | 접속정보·공통 모델 없음. 필요한 제약: `channels` UNIQUE(department_id, grade) 기본 채널, `channel_messages` UNIQUE(channel_id, author_id, client_nonce)와 UNIQUE(channel_id, reference_notice_id), notices revision/status CAS, 게시 전이와 outbox 기록의 단일 트랜잭션 |
| outbox 테이블·재시도 워커 | NOT_IMPLEMENTED | `NoticeService.deliver`가 소비자 계약(멱등)만 제공. 현재는 publish 요청 안에서 동기 호출 |
| 실시간 채팅(WebSocket/SSE) | NOT_IMPLEMENTED | 화면에 "실시간 수신 미연결" 표시와 수동 새로고침만 제공. TC-007 실시간 수신은 NOT_RUN |
| 요청 제한·감사 로그 | NOT_IMPLEMENTED | NFR-SEC 요청 제한, 공지 감사 기록은 공통 미들웨어/감사 원장 필요 |
| 프런트 타입검사·빌드·브라우저 | NOT_RUN(FE 통합) | `apps/web` 패키지·shell·`src/lib/api.ts`가 다른 브랜치에서 작성 중. 의존성 설치 금지 지시로 실행하지 않음 |
| 2계정·DB 영속·390/1280 화면·E2E | NOT_RUN | 위 차단 해소 후 TC-V1-DEPT-001/002/005, TC-V1-NOT-001/002, TC-V1-X01로 실행 |

## 7. 프런트 통합 메모

- `index.tsx`의 `CampusPage`는 `departmentId`를 shell(인증 세션)에서 받는다. 없으면 연결 준비 상태만 보여 준다.
- `api.ts`는 `../../lib/api`의 `requestData`, `model.ts`는 `ApiError(code/status/requestId)`를 가정한다. `requestData`가 `/api/v1`을 자동으로 붙인다면 `BASE`를 비워야 한다.
- 503은 "서버 연결 준비 중"으로 표시하며 성공 목업을 보여 주지 않는다. 전송한 메시지는 서버 응답으로 받은 레코드만 목록에 추가하며 DB 영속 확인 전 "저장 완료" 문구를 쓰지 않는다. 실패 시 같은 `client_nonce`로 재시도해 중복을 막는다.
- 공지 작성·개정 UI는 역할 판별 계층이 생긴 뒤 추가한다(현재 읽기 전용). `types.ts`는 OpenAPI 생성 타입으로 교체 대상이다.

## 8. 다음 실행 가능 태스크

1. root: 공통 auth `ActorResolver`와 MariaDB 어댑터 연결 후 `build_campus_router` 장착, OpenAPI 스냅샷·프런트 타입 재생성.
2. DB 담당: 위 유일 제약을 포함한 마이그레이션, notice outbox 테이블과 재시도 소비자.
3. 통합 후 2계정 E2E(TC-V1-X01) 및 실시간 전송 방식 결정.
