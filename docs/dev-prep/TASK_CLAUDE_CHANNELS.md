# TASK_CLAUDE_CHANNELS — DEMO 채널 신청 체험과 운영 게이트 안내 (부분 구현)

- 상태: 2026-10-30 **PARTIAL / TESTED (격리된 DEMO 샌드박스)**. Claude 작성 당시 NOT_RUN과 이후 Codex 실제 검증 결과를 아래에 구분한다. 전체 FR·운영 권한 완료를 주장하지 않는다.
- FR: FR-DEPT-003, FR-DEPT-004 (DEMO 신청 부분), FR-NOT-004, FR-ADM-001~003 (읽기 전용 게이트 안내만)
- 이 작업은 관리자 기능·공지 열람 통계·공식 채널 승인을 **완성하지 않는다.**

## 범위와 경계
- 저장: `DemoChannelsStore` 프로세스 메모리(DEMO/PROCESS_MEMORY). 재시작 시 초기화. **MariaDB 영속화 아님, 운영 권한 검사 아님.**
- 기존 `channels` 기능의 저장소 계약은 변경하지 않았다. 실제 채널·메시지·교직원/관리자 권한을 만들지 않는다.
- 실DB 시드 없음. 모든 제목은 목적·종류로 고정 생성되며 자유 입력 없음.
- 미마운트: 루트 소유자가 `app.include_router(router, prefix="/api/v1")`, `app.dependency_overrides[get_actor] = <현재 공통 actor UUID>`, `app.state.demo_channels = DemoChannelsStore()`를 설정해야 한다. 미설정 시 503.

## API (`/api/v1/me/demo-channels`, 모든 응답 `Cache-Control: private, no-store`)
| 메서드 | 경로 | 요청 | 응답 `data` |
| --- | --- | --- | --- |
| GET | `/me/demo-channels` | — | `DemoChannelRequestList {items, per_user_limit, record_source:"DEMO", persistence:"PROCESS_MEMORY"}` (본인 것만) |
| POST | `/me/demo-channels` | `{purpose: study\|project\|social, requested_kind: FREE\|OFFICIAL, consent: true}` 그 외 필드 400 | 201 `DemoChannelRequestView` |
| DELETE | `/me/demo-channels/{uuid}?revision=N` | — | `{id, cancelled:true}`; 타인/없음 404, 개정 불일치 409 |

`DemoChannelRequestView`: `id, purpose, requested_kind, title, status(CREATED|PENDING_REVIEW), revision, created_at, official_badge:false, real_review:"NOT_OPERATED", record_source, persistence`. 소유자 ID 미노출.
- FREE → `CREATED`. OFFICIAL → `PENDING_REVIEW` 고정; 승인·배지 전이 메서드/엔드포인트 없음.
- 한도: 사용자당 20건(초과 409), 전체 200건(초과 503).

## 파일
- BE: `services/api/app/features/demo_channels/{__init__,models,store,router}.py`
- 테스트: `services/api/tests/test_demo_channels.py`
- FE: `apps/web/src/features/demo-channels/{api.ts,index.tsx,OperationalGates.tsx,index.test.tsx}` — `default DemoChannels({sessionGeneration})`, `OperationalGates`(읽기 전용, 요청 없음)

## 남은 위험·후속
- 전역 라우트/화면 연결, OpenAPI 스냅샷·FE 타입 생성 갱신은 루트 소유자 작업.
- 실제 공식 채널 검토, 역할 부여, 공지 열람 통계는 정책 승인(OPEN-002/003) 후 별도 태스크.

## Codex 실제 검증 및 독립 보완 — 2026-10-30
- 관련 요구사항: FR-DEPT-003/004 일부; FR-NOT-004/FR-ADM-001~003은 안내만; NFR-SEC-002/003, NFR-DATA-003, NFR-UX-001. 기존 92개 FR ID 보존.
- Claude builder 종료 후 Codex가 제한 소스/테스트를 읽었다. 추가 FE 보완도 Claude 단일 세션 종료 후에만 Codex가 수정했다. 동시 쓰기 없음.
- BE: pytest tests/test_demo_channels.py **21 PASS** 직접 확인. scoped Ruff check/format **5파일 PASS**.
- FE: vitest run src/features/demo-channels --maxWorkers=2 **11 PASS**, npm run typecheck **PASS**. git diff --check PASS. 실제 GitHub 새 HEAD CI는 PR에서 기록한다.
- POST 영수증의 id/목적/종류/상태/개정이 GET에서 정확히 확인돼야 성공으로 표시한다. DELETE는 동일 id의 취소 영수증과 재조회 행 부재를 확인한다. 불일치·잔존 행은 미확인 오류다.
- 네트워크/잘못된 응답/503 등 결과 불명 POST는 중복 재생성하지 않으며 동의를 폐기하고 쓰기를 잠근다. 사용자가 명시 재조회 후 새 동의를 해야 새 신청을 할 수 있다. 401/403은 동일 세대 전체 읽기/쓰기 잠금·내용/동의 삭제, 새 세대만 재개한다.
- keyed/layout cleanup·same-tick ref 잠금·계정 A의 늦은 응답이 계정 B의 동의를 지우지 않는 회귀를 포함한다.
- 미검증: 실제 App/전역 router·현재 공통 인증 바인딩·브라우저·MariaDB·다중 워커·운영 배포 **NOT_RUN**. 기본 actor/store503·미마운트를 이 PR에서 활성화하지 않았다. PROCESS_MEMORY 데이터는 재시작 시 소실되고 공식 학적/권한/승인/LLM 결과가 아니다.
- NAV/진행 CSV·공통 App/router/auth/config/DB/lock는 root 단일 소유라 수정하지 않았다. 후속 root 통합은 별도 HEAD의 실제 검증이 필요하다.
