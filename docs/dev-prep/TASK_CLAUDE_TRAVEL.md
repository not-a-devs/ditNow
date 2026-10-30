# TASK_CLAUDE_TRAVEL — FR-CAMP-002 수동 이동 여유 계산 통합 준비

- 상태: **PARTIAL / TESTED (격리 단위·HTTP·FE)**. Claude 작성 당시 실행은 NOT_RUN이었으며, 아래 Codex 독립 검증 결과를 구분한다.
- 범위: 기존 순수 계산 `calculate_travel`·`build_travel_router`·`CampusTravelPage` 재사용. 루트 마운트·메뉴 연결은 루트 소유자 작업이며 이 태스크에서 수정하지 않음.

## 변경 파일
| 파일 | 내용 |
| --- | --- |
| `services/api/app/features/campus_travel/router.py` | 중복 `TravelRoute` 제거 → `app.features.collaboration.router.PrivateNoStoreRoute` 재사용. `CALCULATE_PATH` 상수, 선택적 서버측 `actor` 의존성 주입(키워드), 비활성 시 identity 해석 전 503 |
| `services/api/app/features/campus_travel/__init__.py` | 통합용 export |
| `services/api/tests/test_campus_travel_live.py` | 활성 라우터 실제 HTTP POST 검사(신규) |
| `apps/web/src/features/campus-travel/index.tsx` | named export `CampusTravelPage` 추가(default 유지) |
| `apps/web/src/features/campus-travel/index.test.tsx` | 응답 가드·경계·중복 제출/편집 abort 경합 테스트 추가 |

## 통합 계약
- 백엔드 export: `app.features.campus_travel` → `build_travel_router`, `calculate_travel`, `TravelInput`, `TravelResult`, `NOTICE`, `CALCULATE_PATH`.
- 루트 마운트 예: `app.include_router(build_travel_router(enabled=True, actor=<공통 현재 actor 의존성>), prefix="/api/v1")`.
  - `actor`를 주입하면 `None` 또는 빈 `user_id` → 401 `UNAUTHORIZED`. 주입하지 않으면 무상태 계산만 수행(개인 데이터 없음).
  - `enabled=False`(기본) → 본문 검증·actor 해석 전에 503 `UNAVAILABLE`.
- 경로: `POST /api/v1/campus-travel/calculate`
- 요청 DTO `TravelInput`(추가 필드 금지): `previous_ends_at`, `next_starts_at`(`20YY-MM-DDTHH:MM:SS` + `Z`/`±HH:MM` 필수), `estimated_travel_minutes`(strict int 0~1440). 두 시각 차이 절댓값 ≤ 7일.
- 응답 `SuccessResponse[TravelResult]`: UTC 정규화 시각, `gap_seconds`, `travel_seconds`, `remaining_seconds`, `status`(`OVERLAP|INSUFFICIENT|NO_MARGIN|HAS_MARGIN`), `estimate_source="USER_INPUT"`, `calculation_version="manual-travel-v1"`, `notice`.
- 모든 성공·오류 응답 `Cache-Control: private, no-store`. 오류는 공통 `ErrorResponse`(400/401/500/503).
- 프런트 export: `apps/web/src/features/campus-travel/index.tsx` → `CampusTravelPage`(named + default), `api.ts` → `calculateTravel`, `kstInput`, `validateInput`, `NOTICE`, 타입 `TravelInput`/`TravelResult`.

## 작성한 테스트 (NOT_RUN)
- `test_campus_travel_live.py`: 정확한 응답 계약·UTC 정규화, OVERLAP/INSUFFICIENT/NO_MARGIN 경계, 동일 순간의 KST/UTC 입력 동치, KST 연초→UTC 전년도, 7일·1440분 포함 경계, 15종 입력 거부(VALIDATION 공통 봉투), 클라이언트 identity 필드 거부, 잘못된 JSON no-store, 비활성 fail-closed(무효 본문 포함·actor 미해석), 주입 actor 401/허용, 마운트 경로.
- `index.test.tsx`: 시각 echo·타입·버전·notice·임의 거리 필드 거부, 배열/누락 키 거부, 7일·1440분 경계, 겹침 상태 위조 거부, 재제출/편집 시 이전 요청 abort 및 지연 응답 무시, 로컬 검증 알림(전송 없음), 입력 변경 시 결과 초기화, 언마운트 후 지연 성공 무시.
- 기존 `services/api/tests/test_campus_travel.py`는 수정하지 않음(호환 유지 의도).

## 한계·위험
- 실제 지도·거리·공식 이동 시간·접근 가능 동선 없음. 개인 시간표 미연결. DB 저장 없음.
- 루트가 `actor`를 주입하지 않으면 인증 없이 계산 가능(개인 데이터 없음). 운영 권한 검증이 아님.
- 라우트 수준 의존성으로 바뀌어 비활성 라우터는 무효 본문에도 400 대신 503 반환(의도적 fail-closed).
- `PrivateNoStoreRoute` 내부 오류 로그 이벤트명이 `collaboration.request.failed`로 기록됨.
- OpenAPI 스냅샷·생성 타입은 루트 마운트 후 갱신 필요(이 태스크 범위 밖).

## Codex 독립 검증 — 2026-10-30
- Claude 프로세스 종료 후 제한 경로 diff·소스와 테스트를 읽었다. 공통 router/App/인증/DB 수정 없음.
- 기존 + 신규 BE: `python -m pytest -q tests/test_campus_travel.py tests/test_campus_travel_live.py` **59 PASS**.
- FE: `vitest run src/features/campus-travel/index.test.tsx --maxWorkers=2` **35 PASS**. `npm run typecheck`, `npm run build` PASS.
- scoped Ruff check/format **5개 파일 PASS**. npm 잠금 설치는 `npm ci --offline --no-audit --no-fund`로 캐시만 사용했다.
- 실제 운영 서버/마운트/브라우저/DB/지도/공식 이동 규정: **NOT_RUN**. 빌드 성공은 미마운트 모듈의 통합 완료 증거가 아니다.
