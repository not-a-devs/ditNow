# TASK_CLAUDE_PROFILE — DEMO 활동 선호 샌드박스 (FR-AUTH-003 일부)

상태: **PARTIAL / TESTED (격리된 DEMO 샌드박스)**. Claude 작성 당시 실행은 NOT_RUN이었으며 이후 Codex 실제 검증 결과를 아래에 구분한다. 이 PR은 API/App 미마운트·기본503을 유지하며 전체 FR-AUTH-003 완료가 아니다.

## 범위
- 본인 전용 활동 선호 `{interests, skill_level, revision}`만 다룬다. 실명·소개·자유 입력·학과·학년·역할 필드는 없다.
- 기존 `app.features.profiles`는 휴면 상태 그대로이며 정본 신원은 공통 인증 소유자 하나다. 이 모듈은 경쟁 신원/프로필 원장이 아니다.
- 저장소는 **DEMO / PROCESS_MEMORY**다. 프로세스 재시작 시 초기화되며 MariaDB 영속화나 운영 권한 부여로 설명하지 않는다. 실DB 자동 시드 없음.

## 파일
- `services/api/app/features/demo_profile/` — `schemas.py`(DTO·고정 enum), `store.py`(`DemoProfileStore`, Lock·CAS·최대 200 소유자), `router.py`(`router`, `get_actor`, `get_store`), `__init__.py`
- `services/api/tests/test_demo_profile.py`
- `apps/web/src/features/demo-profile/` — `api.ts`, `index.tsx`(default `DemoProfile`), `index.test.tsx`

## API 계약 (`/api/v1` 아래에 루트 소유자가 mount)
| 메서드 | 경로 | 요청 | 응답 |
| --- | --- | --- | --- |
| GET | `/me/demo-profile` | 없음 | `SuccessResponse[DemoProfilePreferences]`, `resource_version=revision` |
| PATCH | `/me/demo-profile` | `DemoProfileUpdate` | 동일 |

- `DemoProfileUpdate`(extra forbid): `interests: list["coding"|"design"|"volunteering"|"career"]`(중복 금지, 최대 4, 정규 순서로 저장), `skill_level: "beginner"|"intermediate"`, `revision: int`(strict, ≥1).
- `DemoProfilePreferences`: 위 3필드 + `record_source: "DEMO"`, `storage: "PROCESS_MEMORY"`. 소유자 UUID는 응답에 없다.
- 미작성 소유자는 고정 합성 기본값(`[]`, `beginner`, revision 1)을 읽으며 용량을 차지하지 않는다.
- 오류(공통 `ErrorResponse`, 모두 `Cache-Control: private, no-store` — `PrivateNoStoreRoute` 재사용): 400 추가/잘못된 입력, 401 actor 없음/UUID 아님(저장소 해석 전), 409 revision 불일치, 503 actor/저장소 미설정 또는 신규 소유자 200 초과.

## 통합 방법 (루트 소유자, 이 작업에서 수행하지 않음)
```python
from app.features.demo_profile import DemoProfileStore, get_actor, router
app.state.demo_profile = DemoProfileStore()
app.dependency_overrides[get_actor] = <공통 현재 actor의 UUID를 반환하는 의존성>
app.include_router(router, prefix="/api/v1")
```
요청 본문·쿼리·헤더의 actor/학과/역할은 읽지 않는다.

## 프런트
- `DemoProfile({ sessionGeneration })`: 고정 체크박스 4개·수준 라디오 2개, 편집→`변경 내용 확인`→`저장 확정`→PATCH→GET 재조회 비교. 세대 변경·언마운트 시 진행 요청 abort와 상태 초기화, 401/403 시 개인 값 삭제, 409 시 입력 보존. PROCESS_MEMORY 한계 문구 상시 표시.

## 테스트 (작성됨, NOT_RUN)
- BE: 기본 503, 저장소 누락/형식 오류 503, 401 선결, 비UUID actor 거부, 기본값 비할당, 정규 순서 재조회, A/B 격리, 쿼리·헤더 소유자 위조 무시, 신원·학적·역할·출처 추가 필드 400, enum/중복/strict revision 등 입력 400, stale 409, 용량 한도, 생성자 범위, 동시 CAS 단일 승자, 재시작 초기화.
- FE: 응답 가드, 한계 문구·자유 입력 없음, 확인 전 미전송·재조회, 계속 편집, 409 보존, 401 삭제, 503, 계정 세대 abort·이전 결과 무시.
- 실행 명령: `cd services/api && uv run --locked pytest tests/test_demo_profile.py`, `cd apps/web && npm test -- demo-profile && npm run typecheck`.

## 한계·위험
- `apps/web/src/lib/api.ts`의 보호 경로 정규식에 `/me/demo-profile`이 없어 현재 전송 계층은 Bearer 토큰을 붙이지 않는다. 마운트 전 공통 API 소유자가 경로를 추가해야 한다(이 작업의 쓰기 범위 밖).
- OpenAPI 스냅샷·생성 타입·App 라우트·NAV·진행 CSV는 갱신하지 않았다(범위 밖). 미마운트이므로 기본 OpenAPI 드리프트는 없을 것으로 예상하나 미검증.
- 다중 워커 프로세스에서는 워커별로 값이 갈라진다. 단일 프로세스 시연 전용.

## Codex 실제 검증 및 독립 보완 — 2026-10-30
- 관련 요구사항: FR-AUTH-003 일부; NFR-SEC-002/003, NFR-DATA-003, NFR-UX-001. 기존 92개 FR ID 보존.
- Claude builder 종료 후 Codex가 제한 소스/테스트를 읽었다. 추가 FE 보완도 Claude 단일 세션 종료 후에만 Codex가 수정했다. 동시 쓰기 없음.
- BE: pytest tests/test_demo_profile.py **48 PASS** 직접 확인. scoped Ruff check/format **5파일 PASS**.
- FE: vitest run src/features/demo-profile --maxWorkers=2 **16 PASS**, npm run typecheck **PASS**. git diff --check PASS. 실제 GitHub 새 HEAD CI는 PR에서 기록한다.
- PATCH 영수증을 제출 interests/skill_level 및 expected revision+1과 비교하고, GET이 이전 개정 또는 같은 개정의 다른 값이면 성공 안내를 거부한다. 기존 거짓 완료 4사례를 새 회귀로 재현: 수정 전4FAIL → 수정 후4PASS.
- 같은 tick 저장 ref 잠금, 401/403 동일 세대 재조회/쓰기 잠금·개인 draft 삭제, keyed 인스턴스/layout cleanup·StrictMode·지연 응답 폐기 회귀를 포함한다.
- 미검증: 실제 App/전역 router·현재 공통 인증 바인딩·브라우저·MariaDB·다중 워커·운영 배포 **NOT_RUN**. 기본 actor/store503·미마운트를 이 PR에서 활성화하지 않았다. PROCESS_MEMORY 데이터는 재시작 시 소실되고 공식 학적/권한/승인/LLM 결과가 아니다.
- NAV/진행 CSV·공통 App/router/auth/config/DB/lock는 root 단일 소유라 수정하지 않았다. 후속 root 통합은 별도 HEAD의 실제 검증이 필요하다.
