# TASK-U 학생 자유 채널 · 공식 채널 신청 1차 구현 (FR-DEPT-003/004)

2026-10-30 KST · 브랜치 `feat/channels-firstpass-20261030` · 상태 `review` (비활성 라우터, 공통 auth/DB 미연결). 어떤 FR도 VERIFIED가 아니며 실DB 검증은 하지 않았다.

## 1. 범위와 상태

| FR | TC | 이 PR 범위 | 상태 |
|---|---|---|---|
| FR-DEPT-003 목적별 자유 채널 개설·참여·관리 | TC-V1-DEPT-003 | 현재 소속 학과(·학년) 범위 생성, 참여/나가기(본인 멤버십만), 개설자 수정·보관(CAS), 커서 페이지 목록, 내 채널 | IMPLEMENTED(부분) / TESTED(unit, fake) |
| FR-DEPT-004 공식 채널 생성·승인·공식 배지 | TC-V1-DEPT-004 | **신청 제출과 본인 신청 상태 조회만**. 승인·반려·공식 배지 부여·교직원 권한 주장 없음 | 신청: IMPLEMENTED(부분) / 승인·배지: **BLOCKED** |

관련: DEC-007(학생 자유채널 생성 가능, 공식 채널은 권한자 승인·관리), RBAC-DEPT(현재 소속, 전과/휴학 뒤 옛 범위 거부), NFR-SEC(서버 권한·입력 검증), NFR-PRIV(개설자·신청자 user ID 응답 미포함).

범위 밖: 자유 채널 메시지 전송·실시간 전송(WebSocket 등), 파일, 신고·강퇴 등 운영(moderation) 정책, 소유권 이전, 승인자 역할·승인 API, 공식 배지.

## 2. 구현 위치와 재사용

- 백엔드 `services/api/app/features/channels/` — `domain.py`, `ports.py`(UOW Protocol), `service.py`, `schemas.py`, `router.py`, `__init__.py`.
- 재사용(수정 없음):
  - 범위 판정: campus `policy.can_access_channel`/`belongs_to_department`와 `Membership`·`CampusActor`. 자유 채널은 기본 채널과 **같은 규칙**(학년 채널은 정확한 현재 학년, 학년 없는 소속은 학과 전체만)으로 판정한다.
  - 입력 정리: campus `clean_text`(제어·서식 문자 거부, ZWJ만 허용), `check_page_size`.
  - 멱등 키: academics `idempotency`(`claim_for`, `replayed_resource`, `KEY_PATTERN`).
  - 개인 응답 no-store: collaboration `PrivateNoStoreRoute`(성공·오류 모두 `private, no-store`). 오류 로그 이벤트 이름이 `collaboration.request.failed`로 남는 한계가 있어, root가 공통 route class를 `app/core`로 옮기는 것을 권장한다.
  - 프런트: campus `StatusView`, `toErrorView`, `intentFor`/`intentAfterFailure`/`isUncertainSendFailure`, 공유 `requestData`.
- 테스트 `services/api/tests/test_channels_support.py`(테스트 전용 fake), `test_channels_service.py`, `test_channels_http.py`.
- 프런트 `apps/web/src/features/channels/` — `index.tsx`(default `ChannelsPage({departmentId, grade})`), `api.ts`, `types.ts`(손으로 맞춘 거울 타입), `fixtures.test-data.ts`, `api.test.ts`, `index.test.tsx`.

## 3. API 계약 (root 장착 후 `/api/v1` 기준, 현재 미장착)

| 메서드·경로 | 권한(서버, 트랜잭션 안 현재 소속) | 성공 | 주요 실패 |
|---|---|---|---|
| GET `/departments/{id}/free-channels?before&limit≤50` | 해당 학과 현재 소속 | ACTIVE, 학과 전체 + 본인 학년 범위 | 400, 401, 403, 503 |
| GET `/me/free-channels` | 인증 | 본인 멤버십 중 **현재 범위 안**인 채널만 | 400, 401 |
| POST `/free-channels` + `Idempotency-Key` | 해당 범위 현재 소속 | 201 / 같은 키·내용 재전송 200 `replayed` | 400, 403, 409(이름 중복·개설 한도·같은 키 다른 내용) |
| GET `/free-channels/{id}` | 범위 소속 | `my_role`, `is_official=false` 고정 | 403, 404 |
| PATCH `/free-channels/{id}` `{name,description,expected_revision}` | 개설자 + 현재 범위 | revision+1 | 403, 409(CAS·보관됨·이름 중복) |
| POST `/free-channels/{id}/archive` `{expected_revision}` | 개설자 + 현재 범위 | 보관, 대기 신청 자동 CANCELLED, 같은 개정 재호출 멱등 | 403, 409 |
| POST `/free-channels/{id}/join` | 범위 소속 | 이미 참여면 `changed=false` | 403, 404, 409(보관·정원) |
| POST `/free-channels/{id}/leave` | 본인 멤버십 | 없으면 `changed=false`, 소속 변경 후에도 본인 정리 허용 | 409(개설자), 403(비멤버·범위 밖) |
| POST `/free-channels/{id}/official-requests` `{reason}` + 키 | 개설자 + 현재 범위, ACTIVE | 201 `PENDING`, `review_state=BLOCKED_APPROVER_POLICY` | 400, 403, 409(대기 중 신청 존재·보관) |
| GET `/me/official-channel-requests`, `/me/official-channel-requests/{id}` | 본인 | 본인 신청만 | 404(타인 신청과 부재를 구분하지 않음) |

순서: 서비스 미주입 → 503, 인증 브리지 미주입 → 503, 인증 실패(`None`) → 401, 이후 400/403/404/409. 기본 학과·학년 채널 ID로 자유 채널 API를 호출하면 403이며 기본 채널은 수정·보관·참여 조작되지 않는다. 승인·반려·배지·PUT/DELETE 경로는 존재하지 않는다(테스트로 고정).

## 4. 설계 기본값 (학교 정책 아님)

- 이름 40자, 설명 500자, 신청 사유 10~1000자 — NFC 정규화 후 코드 포인트 기준. 이름 유일성 키는 NFKC+casefold+공백 축약, 범위(학과, 학년)별 ACTIVE 채널 안에서만.
- 개설자당 범위별 ACTIVE 5개, 채널 정원 300명, 페이지 최대 50.
- 개설자는 나갈 수 없고 보관만 가능. 소유권 이전·멤버 강퇴는 운영 정책 미정으로 미구현(개설자가 다른 사람의 멤버십을 바꿀 수 없음).
- 관리 권한은 저장된 OWNER 멤버십 **그리고** 채널 `owner_id` 일치 **그리고** 현재 범위 소속을 모두 요구한다.
- 신청은 채널을 공식으로 바꾸지 않으며 채널 개정 번호도 바꾸지 않는다. 응답 스키마가 `is_official: Literal[False]`이고 프런트 가드도 `true`를 잘못된 응답으로 거부한다.

## 5. 동시성·원자성 계약 (`ports.py`)

잠금 순서 `scope(department, grade) → channel(id)`. 생성·수정·보관은 scope 잠금 뒤 이름 유일성·개설 한도를 판단하고, 참여·나가기·신청은 channel 행 잠금(`FOR UPDATE`) 뒤 멤버십·정원·상태·대기 신청을 읽는다. 잠금 뒤 판단 읽기는 현재 읽기(READ COMMITTED 또는 locking read)여야 한다. `update_*`는 CAS, `insert_*`는 멱등 claim과 같은 트랜잭션. MariaDB의 NULL 중복 허용 때문에 학과 전체(grade NULL) 범위는 별도 scope 행 잠금이 필요하다.

**검증 수준:** 테스트 fake는 RLock 하나로 직렬화하고 스냅샷으로 롤백한다. 서비스가 판단 전에 잠금을 호출하는 순서와 직렬화 시 결과(정원 초과 없음, 롤백 시 claim까지 제거)만 증명한다. InnoDB 잠금·격리·데드락은 **NOT_RUN**.

## 6. 실제 실행한 검사 (2026-10-30, Windows, Python 3.13 / uv, Node 로컬)

`services/api`:
- `uv run --locked ruff check .` — All checks passed.
- `uv run --locked ruff format --check .` — 137 files already formatted.
- `uv run --locked pytest -q` — 776 passed(channels 2개 파일 97). 경고 1건은 기존 Starlette TestClient/httpx 경고.

`apps/web`:
- `npm ci` — 0 vulnerabilities.
- `npm test -- src/features/channels` — 2 files, 15 passed. 전체 `npm test` — 23 files, 315 passed.
- `npm run typecheck` — 오류 없음. `npm run build` — 성공(단 `App.tsx`가 channels를 import하지 않아 번들 미포함).
- `npm run api:types:check` — 공개 스냅샷과 일치(channels 경로는 스냅샷에 없음).

테스트가 증명하는 것: 미주입 11경로 503(서비스만 주입해도 503), 미인증 401·무기록, 전역 앱 OpenAPI에 경로 없음, 승인/배지 경로 부재; 타 학과·타 학년·무소속 생성/조회/참여 403; 소속 변경(revocation) 뒤 개설자 관리·조회 403, 내 채널 목록에서 숨김, 본인 나가기는 허용; 기본 채널 6개 조작 403·무기록; 멱등 재전송·다른 내용 409·소속 상실 뒤 재전송 403; NFC/NFKC 이름 충돌, bidi·ZWSP·제어문자 400, ZWJ 이모지 허용; CAS 409, 보관 멱등·보관 후 참여/수정 409·대기 신청 CANCELLED; 정원·개설 한도; 잠금 호출 순서; 커서 페이지 경계; 응답에 `owner_id`/`requester_id` 없음, 400 응답에 입력 반사 없음; 프런트 `/api/v1` 접두사 1회, UUID 아닌 ID는 요청 전 거부, `is_official:true`·알 수 없는 신청 상태 응답 거부, 503/403 화면, 서버 역할 기반 버튼, 불명확 실패 후 같은 내용 재시도 시 같은 키, 신청 후 "승인 절차 보류" 표시.

## 7. 미검증·차단

| 항목 | 상태 | 연결 조건 |
|---|---|---|
| 공용 앱 장착·OpenAPI·생성 타입 | BLOCKED(root 소유) | `get_channels_actor`(검증 세션→user ID)와 `get_channels_service`(MariaDB UOW)를 override 후 `/api/v1`에 include, 스냅샷·`api.d.ts` 재생성, `types.ts` 교체 |
| 공통 인증 브리지(현재 신원) | BLOCKED(auth) | 세션 검증만 하고 소속은 UOW `current_memberships()`가 트랜잭션 안에서 다시 읽음 |
| MariaDB 어댑터·마이그레이션 | BLOCKED(DB) / NOT_RUN | 테이블 `free_channels`, `free_channel_memberships` UNIQUE(channel_id,user_id), `official_channel_requests`(채널당 PENDING 1건), scope 잠금 행, 멱등 claim. 접속·DDL 시도하지 않음 |
| 공식 채널 승인·반려·공식 배지 | **BLOCKED(사람 승인)** | 승인 권한자 역할(교직원/관리자) 정책과 공통 RBAC 확정 전 구현·활성화 금지 |
| 자유 채널 대화·실시간 전송 | NOT_IMPLEMENTED | campus 메시지 계약 확장 또는 실시간 전송 방식 결정 후 별도 태스크 |
| 운영(신고·강퇴·소유권 이전) | NOT_IMPLEMENTED | 정책 미정 |
| 웹 shell 장착·실제 브라우저·2계정 E2E | NOT_RUN | root가 학과 메뉴에 `ChannelsPage`를 연결하고 세션 소속을 전달 |
| GitHub Actions CI | 미확인 | root가 PR HEAD의 web-ci·python-api-ci 확인 |

## 8. 다음 실행 가능 태스크

1. root: auth 브리지·MariaDB UOW 연결 후 라우터 장착, 스냅샷·타입 재생성, 공통 no-store route class 정리.
2. DB 담당: §7 테이블·제약·scope 잠금 행 마이그레이션과 실DB 동시성 검사.
3. 사람 승인: 공식 채널 승인자 역할·배지 표시 정책(DEC-007 세부) — 승인 전 BLOCKED 유지.
