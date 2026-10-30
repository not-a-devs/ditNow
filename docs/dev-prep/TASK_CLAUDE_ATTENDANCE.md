# TASK_CLAUDE_ATTENDANCE — DEMO 모바일 학생증·가상 숫자 코드 출석 샌드박스

> 상태: 2026-10-30 · 빌더 Claude · FR-ATT-003, FR-ATT-004 · 테스트·리뷰·커밋은 Codex 담당
> 검증: Claude 작성 당시 **NOT_RUN**. 이후 Codex의 격리 테스트 결과는 아래에 별도 기록하며 실제 통합·DB·공식 출결 검증과 구분한다.

## 범위와 한계
- 명시적 **DEMO / PROCESS_MEMORY** 시연 기능이다. 서버 재시작 시 초기화되며 MariaDB 영속화, 실제 출결 원장, 운영 권한 부여가 **아니다**.
- 카드는 고정 합성 별칭만 보여 준다. 학번·실명·소속·유효 신분 증명·QR을 제공하지 않는다(`valid_credential=false`, `qr_enabled=false`).
- 출석 코드는 화면에 공개되는 고정 가상 코드 `123456`이다. 블루투스·QR·위치·재실 확인을 하지 않으며 학교 시스템(캠퍼스락 등)과 무관하다.
- 실DB·마이그레이션·시드·전역 파일(App, 내비게이션, `lib/api.ts`, 공통 인증, factory, 전역 라우터) 변경 없음. 라우터는 **미마운트** 상태다.

## 파일
| 영역 | 경로 |
| --- | --- |
| BE 저장소 | `services/api/app/features/demo_attendance/store.py` |
| BE DTO | `services/api/app/features/demo_attendance/schemas.py` |
| BE 라우터 | `services/api/app/features/demo_attendance/router.py` |
| BE 공개 export | `services/api/app/features/demo_attendance/__init__.py` |
| BE 테스트 | `services/api/tests/test_demo_attendance.py` |
| FE 클라이언트·가드 | `apps/web/src/features/demo-attendance/api.ts` |
| FE 화면 | `apps/web/src/features/demo-attendance/index.tsx` |
| FE 테스트 | `apps/web/src/features/demo-attendance/index.test.tsx` |

## API (`/api/v1` 아래 마운트 시)
| 메서드·경로 | 요청 | 성공 | 오류 |
| --- | --- | --- | --- |
| `GET /me/demo-attendance/card` | 없음 | 200 `SuccessResponse[DemoCardView]` | 401/503 |
| `GET /me/demo-attendance/state` | 없음 | 200 `SuccessResponse[DemoAttendanceState]` (본인만) | 401/503 |
| `POST /me/demo-attendance/check-in` | `{ "code": "^[0-9]{6}$" }` (추가 필드 금지) | 최초 201, 반복 200 `SuccessResponse[CheckInResult]` (`replayed`) | 형식 오류 400, 코드 불일치 422, 401, 용량 초과 503 |

- 모든 응답(오류 포함)은 `PrivateNoStoreRoute`로 `Cache-Control: private, no-store`.
- DTO: `DemoCardView{card{mode,storage,display_alias,card_label,valid_credential,qr_enabled,notice},session{session_label,method,simulation_code,notice}}`, `DemoAttendanceState{mode,storage,method,checked_in,checked_in_at}`, `CheckInResult{mode,storage,method,checked_in_at,replayed}`.

## 루트 통합 계약 (루트 소유자 작업)
- `app.include_router(demo_attendance.router, prefix="/api/v1")`
- `app.dependency_overrides[demo_attendance.get_actor] = <공통 현재 사용자 UUID 반환, 미인증 시 None>`
- `app.state.demo_attendance = DemoAttendanceStore()` — 둘 중 하나라도 없으면 503으로 닫힌다.
- FE: `import DemoAttendance from './features/demo-attendance'` 후 `<DemoAttendance sessionGeneration={...} />`. 세대 변경/언마운트 시 카드·입력·결과·알림을 초기화하고 진행 중 요청을 중단한다.

## 테스트 (작성됨, NOT_RUN)
- BE: 기본 actor 503, store 부재 503, 미인증 401(기록 없음), 비UUID actor 401, 카드 DEMO·자격 없음·사용자 ID 미노출, 최초/반복 체크인, 계정 격리, 불일치 422, 형식·추가 필드(user_id/department/role) 400, 쿼리 신원 무시, 용량 제한 503·200 상한, 동시 체크인 1회, 읽기는 소유자 항목 생성 안 함, 모든 응답 no-store.
- FE: 카드·코드·고지 표시, 코드만 전송, 최초/반복 결과, 클라이언트 형식 차단, 422 메시지, 세대 변경 초기화, 늦은 응답 무시·중단, 언마운트 중단, 로드 오류, 응답 가드.

## 위험
- 고정 공개 코드이므로 어떤 출석 증빙도 될 수 없다. 화면 문구로만 구분되므로 시연 시 실제 출결로 오해되지 않게 안내 필요.
- 프로세스 메모리이므로 다중 워커에서는 워커별로 상태가 다르다.
- 실제 출결 세션·교수 확인·정정 흐름(FR-ATT-003 전체)과 모바일학생증 발급·폐기 규칙(FR-ATT-004)은 OPEN-007 정책 보류로 미구현.

## Codex 독립 검증 및 보완 — 2026-10-30
- Claude 종료 후 소스 독립 검토. API의 actor UUID는 서버 dependency만 사용하며 사용자 지정 ID/학과/역할로 상태를 바꿀 수 없다. 실제 운영 인증은 root 통합 범위다.
- method 표식을 검증하지 않는 응답 가드, 401/403 후 기존 카드/입력이 남는 경로를 회귀로 재현했다: 추가 3개 **수정 전 FAIL → 수정 후 PASS**.
- FE는 숫자 코드 시뮬레이션 method와 실제 UTC Z 날짜를 검사하고, 401/403이면 카드·본인 상태·입력·성공 안내를 폐기한다. 동일 tick 중복 제출은 ref 잠금으로 차단한다. StrictMode 취소·세션 세대 reset 회귀 포함.
- BE 전용 `pytest -q tests/test_demo_attendance.py` **30 PASS**; FE 전용 **13 PASS**; TypeScript·빌드 PASS. scoped Ruff check/format PASS(초기 포맷1개 정정).
- npm 잠금 설치는 offline 캐시만 사용. DB·공식 출석·Bluetooth·장치·실브라우저·운영 서버/마운트는 **NOT_RUN**. 전용 테스트는 in-process/mocked transport이며 실제 MariaDB 증거가 아니다.
