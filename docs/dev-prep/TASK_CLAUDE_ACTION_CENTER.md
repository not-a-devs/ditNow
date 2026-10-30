# TASK_CLAUDE_ACTION_CENTER — 가상 시연(DEMO) 액션 센터

- 상태: PARTIAL / TESTED (격리된 DEMO 샌드박스). Claude 작성 당시 NOT_RUN과 이후 Codex 실제 검증을 아래에 구분한다. 전체 FR 완료·운영 통합을 주장하지 않는다.
- FR: FR-HOME-001, FR-HOME-003, FR-AI-001, FR-NOT-005
- 범위: 기존 `action_center` 실제 포트와 **분리된** 명시적 가상 시연 연습. 고정 합성 내용, 서버 프로세스 메모리(`PROCESS_MEMORY`)만 사용하며 재시작 시 초기화된다. MariaDB 저장·운영 권한 검증·학교 시스템 연동이 아니다.

## 파일
- `services/api/app/features/demo_action_center/__init__.py` — `DemoActionCenterStore`, `router`, `get_actor`, `get_store` 내보냄
- `services/api/app/features/demo_action_center/models.py` — DTO
- `services/api/app/features/demo_action_center/store.py` — 스레드 잠금 메모리 저장소
- `services/api/app/features/demo_action_center/router.py` — 라우터(미장착)
- `services/api/tests/test_demo_action_center.py`
- `apps/web/src/features/demo-action-center/{api.ts,index.tsx,index.test.tsx}`

## API (루트가 `/api/v1` 아래 장착)
- `GET /me/demo-action-center/summary` → `SuccessResponse[DemoSummary]`
  - `mode:"DEMO"`, `storage:"PROCESS_MEMORY"`, `rule_based:true`, `ai_generated:false`, `school_connection:"NOT_CONNECTED"`
  - `cards`: 고정 3개(`demo-class-1`/`demo-task-1`/`demo-notice-1`), `record_source:"DEMO"`, 고정 내부 링크(`/app/classrooms`, `/app/department`)
  - `notifications`: 행위자별 고정 3개, `id`는 최초 접근 시 무작위 UUID 할당(소유자 UUID와 무관), `read`, `revision`, `delivery:"IN_APP_ONLY"`
  - `unread_count`
- `POST /me/demo-action-center/notifications/{id}/read` 본문 `{revision:int}`(StrictInt, 추가 필드 거부) → `SuccessResponse[DemoReadResult]{notification, already_read, unread_count}`, `resource_version`=새 revision
  - 미확인·타인 ID: 동일 404 / 미읽음+revision 불일치: 409 / 이미 읽음: 200 `already_read:true`, revision·집계 불변

## 보안·실패 기본값
- `get_actor()` 기본 503; 루트가 공통 현재 행위자 UUID로 override. `None`이면 401. 헤더·쿼리·본문으로 행위자/학과/역할 지정 불가.
- `get_store(request)`는 `request.app.state.demo_action_center`가 `DemoActionCenterStore`가 아니면 503.
- `PrivateNoStoreRoute`(collaboration) 재사용: 성공·오류 모두 `Cache-Control: private, no-store`, 공통 오류 envelope.
- 소유자 최대 200(초과 시 503), 단일 `threading.Lock`, 반환 DTO는 내부 상태와 비공유 복사본.
- 실DB 자동 시드·LLM·개인 학적 조회·푸시/이메일/자동 발송·공식 열람 통계 없음.

## 프런트
- `export default function DemoActionCenter({ sessionGeneration })`: 로딩·일반 오류(다시 시도)·401/403(내용 비움 후 동일 세대 재요청 잠금)·충돌(메시지 후 재조회). 새 세대는 keyed 새 인스턴스로 초기화하며 layout cleanup에서 진행 요청을 즉시 abort한다. 응답은 정확 키·고정 링크·DEMO 플래그·미읽음 수·현재 알림 영수증 개정과 GET 재조회 일치로 검증한다. 전역 라우트·내비게이션 미연결.

## 테스트 (NOT_RUN)
- BE: 기본 미장착, 기본 503·스토어 미설치 503·401, 고정 요약 플래그·링크, 소유자별 ID 안정·비유출·격리, 404 동일성, 409 CAS, 이미 읽음 멱등·중복 차감 없음, 식별 필드/헤더/쿼리 무시, 용량 503, ID 충돌 fail-closed, reset, 동시 읽음 1회 집계, 반환값 비공유, no-store 헤더.
- FE: 텍스트 전용 렌더·고정 링크·배지, 변조 응답 거부, 503 재시도, revision 요청·성공 후 표시, already_read 집계, 409 재조회, 401 비움, 세션 세대 초기화·abort.

## 한계·후속
- 루트 장착·`app.state` 설치·공통 행위자 주입·OpenAPI/`api.d.ts` 재생성·화면 배치는 다른 소유자 작업.
- 메모리 상태는 다중 워커 간 공유되지 않으며 재시작 시 사라진다.
- `NAV.md`·진행 CSV는 소유 범위 밖이라 미수정.

## Codex 실제 검증 및 독립 보완 — 2026-10-30
- 관련 요구사항: FR-HOME-001/003, FR-AI-001, FR-NOT-005 일부; NFR-SEC-002/003, NFR-DATA-003, NFR-UX-001. 기존 92개 FR ID 보존.
- Claude builder 종료 후 Codex가 제한 소스/테스트를 읽었다. 추가 FE 보완도 Claude 단일 세션 종료 후에만 Codex가 수정했다. 동시 쓰기 없음.
- BE: pytest tests/test_demo_action_center.py **22 PASS** 직접 확인. scoped Ruff check/format **5파일 PASS**.
- FE: vitest run src/features/demo-action-center --maxWorkers=2 **12 PASS**, npm run typecheck **PASS**. git diff --check PASS. 실제 GitHub 새 HEAD CI는 PR에서 기록한다.
- 신규 읽음 영수증의 개정 증가(입력+1)와 동일 card/id를 검증하며, 이미 읽음 replay는 개정 후퇴를 거부한다. 증가 없는 영수증 회귀 수정 전FAIL → 수정 후PASS.
- POST 뒤 GET에 동일 알림의 읽음 상태/개정이 있어야 확인한다. 불일치이면 완료로 처리하지 않고 안내한다. 같은 tick ref 잠금, 401/403 동일 세대 잠금·내용 삭제, keyed/layout cleanup·세대 전환 abort 회귀 포함.
- 미검증: 실제 App/전역 router·현재 공통 인증 바인딩·브라우저·MariaDB·다중 워커·운영 배포 **NOT_RUN**. 기본 actor/store503·미마운트를 이 PR에서 활성화하지 않았다. PROCESS_MEMORY 데이터는 재시작 시 소실되고 공식 학적/권한/승인/LLM 결과가 아니다.
- NAV/진행 CSV·공통 App/router/auth/config/DB/lock는 root 단일 소유라 수정하지 않았다. 후속 root 통합은 별도 HEAD의 실제 검증이 필요하다.
