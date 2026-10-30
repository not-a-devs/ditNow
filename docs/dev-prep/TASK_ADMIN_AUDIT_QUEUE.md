# TASK-ADMIN-AUDIT — FR-ADM-002 운영 감사 큐 (DEMO, 휴면)

- 현재 상태: **독립 모듈 TESTED / 통합 PARTIAL**. Claude 작성·교정 후 Codex 실제 검증 결과는 마지막 절을 따른다. 아래 NOT_RUN은 Claude 작성 시점 기록이다.
- 보정(2026-10-30): 초기 테스트는 Claude가 작성하고 Codex가 실행했다. pytest 30건 중 1건 FAIL(타 owner 테스트가 문자열 id로 `service.get` 호출), Vitest의 비정상 경로 동기 throw 기대 오류가 발견되어 보정 중이다. 함께 보정한 내용: 화면의 로컬 '권한 다시 확인' 버튼 제거(401/403 후에는 상위 세션 세대가 바뀔 때만 재활성), `can_review` 확인을 저장소 RLock 안으로 이동(거부 시 owner 큐 미할당 테스트 추가), PATCH 영수증이 제출한 분류/처리 값·다음 상태와 일치해야 하고 `isItem`은 PENDING 1/CLASSIFIED 2/RESOLVED 3 고정 흐름만 허용(잘못된 영수증 음성 테스트 추가). 보정 후 테스트는 **NOT_RUN**이며 최종 결과는 Codex가 확인한다.
- 범위: 공지/게시물/신고 감사 처리 workflow를 **고정된 가상 메타데이터**만으로 시연. 실제 신고·게시물 본문, 익명 작성자 UUID/이름, 사용자 식별자, 가져온 개인정보는 다루지 않음.
- 저장: `DEMO` / `PROCESS_MEMORY` / `official_effect=false` / `restart_reset=true`. 프로세스를 재시작하면 초기화됨. 실제 제재나 공식 효력은 없음.
- 실제 인증·DB·권한 부여, 승인은 하지 않았으며 그런 주장도 하지 않음.

## FR / NFR / RBAC
| ID | 내용 | 구현 |
|---|---|---|
| FR-ADM-002 | 감사 검색·처리 workflow | 목록(status/category 필터), 상세, PATCH 단계 전이 |
| NFR 보안 | 서버 신뢰 actor, no-store, 안전한 오류 | `get_admin_audit_actor` 기본값 503, 모든 응답(오류 포함) `Cache-Control: private, no-store` |
| NFR 동시성 | CAS, 상한 | RLock, revision 정확 일치, owner 수 상한 64, owner별 idempotency 키 32개(FIFO) |
| RBAC | 현재 권한 | `can_review(user_id) is True`를 **매 요청마다** 다시 확인. 실패하면 403, 포트 예외는 503 |

## API 계약 (마운트 안 함, prefix `/api/v1` 가정)
공통: 성공 응답은 `SuccessResponse{data,resource_version,server_time}`, 오류 응답은 `ErrorResponse{code,message,field_errors,retryable,request_id}`.

- `GET /admin-audit-queue?status=PENDING|CLASSIFIED|RESOLVED&category=NOTICE|POST|REPORT` → `data: {items: AuditItem[≤20], meta}`
- `GET /admin-audit-queue/{id:uuid}` → `data: AuditItem`
- `PATCH /admin-audit-queue/{id:uuid}` (`Idempotency-Key` 선택, `^[A-Za-z0-9-]{16,100}$`)
  - body(extra forbid): `{revision:int(strict,1..1e6), note_code: DEMO_CHECKED|DEMO_POLICY_REVIEW, classification?: REVIEW_NEEDED|NO_ACTION, resolution?: KEEP_DEMO|RESOLVE_DEMO}`. classification과 resolution 중 정확히 하나만 보내야 함.
  - `PENDING` + classification → `CLASSIFIED`, `CLASSIFIED` + resolution → `RESOLVED`, revision +1
  - `RESOLVED`는 변경 불가. 단계 순서가 틀리거나 revision이 다르면 409
  - 같은 키·같은 본문·같은 id → 저장된 영수증 재생. 같은 키로 다른 본문이나 다른 id → 409
- `AuditItem = {id, category, demo_label: DEMO_ITEM_NN, status, classification|null, resolution|null, note_code|null, revision, meta}`
- `meta = {source_kind:"DEMO", storage:"PROCESS_MEMORY", official_effect:false, restart_reset:true}`
- 오류: 400 VALIDATION / 401 actor 없음 / 403 can_review 아님 / 404 미존재·타 owner 항목 / 409 CAS·상태·키 충돌 / 503 휴면·서비스 미주입·owner 상한·권한 포트 장애

## 가정
- actor는 신뢰할 수 있는 서버 identity bridge가 `dependency_overrides`로 주입함. 클라이언트가 보낸 owner/role 값은 받지 않음(extra forbid).
- 서비스는 `app.state.admin_audit_queue`에 `AdminAuditQueueService` 인스턴스가 있을 때만 동작하고, 없으면 503.
- 시연 항목 6개는 actor별로 `uuid5(namespace, "{owner}:{n}")`로 결정적으로 생성됨. 다른 actor 항목은 404.

## 블로커 / TODO
- BLOCKED: 실제 운영자 역할(staff/admin) 정의와 부여, 익명 작성자 조회 정책은 발명하지 않음. `can_review` 포트에는 실제 연결이 없음.
- BLOCKED: `apps/web/src/lib/api.ts`의 `protectedPath`에 `/admin-audit-queue`가 없어 Bearer가 붙지 않음. 공용 파일이라 수정하지 않았음. 통합할 때 공용 소유자가 추가해야 함.
- TODO: router·App route 마운트, `app.state` 주입, 인증 shell의 `sessionGeneration` 전달(모두 금지 범위). 감사 로그 연동과 MariaDB 저장은 미구현.

## 파일 소유
- `services/api/app/features/admin_audit_queue/{__init__,models,service,router}.py`
- `services/api/tests/test_admin_audit_queue.py`
- `apps/web/src/features/admin-audit-queue/{api.ts,index.tsx,api.test.ts,index.test.tsx}`
- `docs/dev-prep/TASK_ADMIN_AUDIT_QUEUE.md`

## TC (작성만 함, 미실행)
- BE: 미마운트·기본 503(actor 없음/서비스 없음/타입 불일치), 고정 메타데이터만 노출(작성자·본문 키 없음), actor별 결정성과 재시작 초기화, enum 필터 400, 전체 수명주기·CAS·RESOLVED 불변, 단계 순서 오류 409, strict body(문자열/bool/float revision, extra owner_id/role/body, 소문자 enum) 400 후 미변경, 잘못된 UUID 400 / 미존재 404, 타 owner 404 및 미변경, can_review 매 요청 재확인과 철회 즉시 403, truthy 아닌 True 거부, 포트 예외 503(내부 문구 비노출), owner 상한, idempotency 재생·다른 본문 409·owner 격리·FIFO 상한, 동시 같은 revision PATCH 1건만 성공, 동시 신규 owner 상한.
- FE: 런타임 가드(추가 키·official_effect·상태 불일치 거부), prefix 1회, enum 쿼리, PATCH body·키·영수증 검증, 기본 503에서 데이터 없음, 확인 체크 없으면 PATCH 안 함·자유 입력란 없음, 재조회가 영수증과 일치할 때만 성공 표시, 불일치하면 성공 표시 안 함, 연속 클릭 시 PATCH 1회, 모호한 실패는 자동 재전송 없음·같은 의도는 같은 키, 401/403이면 상태·확인 전부 삭제 후 상위 세션 세대가 바뀌기 전까지 비활성(로컬 재설정 없음, 같은 세대에서는 추가 요청 없음), 세대 전환 뒤 늦은 목록 무시, 세대 전환 뒤 늦은 PATCH는 재조회·성공 표시 안 함, 409이면 최신 상태 재조회.

## 테스트 명령 (NOT_RUN)
- `cd services/api && python -m pytest tests/test_admin_audit_queue.py -q` — NOT_RUN
- `cd apps/web && npx vitest run src/features/admin-audit-queue` — NOT_RUN
- `cd apps/web && npx tsc --noEmit` — NOT_RUN

## Codex 실제 검증 (2026-10-30)

- FR-ADM-002 / TC-V1-ADM-002. NFR-SEC-002/003/005/006, NFR-PRIV-002/003, NFR-REL-003/004, NFR-UX-001/004/005에 연결하며, 실제 권한·DB 영속성 전체 충족을 주장하지 않는다.
- BE 32 PASS, FE 16 PASS, 전체 신규 웹 570 PASS. 모의 신원·메모리 원장 및 HTTP TestClient 테스트이며 실제 학교·실제 DB 검증이 아니다.
- 잠금 의존성 설치, 신규 웹 타입 검사·빌드, Ruff 정적/포맷 검사, 에이전트 105경로/8스킬, 기능 추적표 92 ID 검사 PASS. 기본 통합 앱은 미마운트로 보존했다.
- 최초 구현은 Claude 제한 세션, 실패 교정은 추가 Claude 제한 세션 1개가 세 작업 트리의 각 허용 기능 파일만 수정했다. Codex는 소스 검토·명령 실행·Ruff 자동 포맷을 수행했다. 테스트 lambda 세 곳의 루프 변수 바인딩은 Codex가 정적 검사 B023을 해소하기 위해 기계적으로 명시했으며 업무 동작을 바꾸지 않았다.
- 미해결 통합 게이트: 현재 공통 신원·운영자 권한 브리지 및 업무 포트 승인, 공통 bearer/no-store 보호 prefix 등록(405 등 라우팅 오류 포함), 앱 연결, 운영 남용 제한, DB/영속 원장이다. 클라이언트 역할 값이나 시연 편의상 true 권한으로 이를 대체하지 않는다.
- 변경 파일 소유 범위 밖의 NAV/상태표/공통 파일 갱신은 root 통합 담당자 소유다. 실제 사용자·관리자 계정 생성·외부 호출·DB·배포·자동 병합은 수행하지 않았다.

- 최종 전체 API 회귀: 1545 PASS, 기존 Starlette 경고 1개. 원격 DB·실제 인증·학교 업무 호출 없이 수행했습니다.
