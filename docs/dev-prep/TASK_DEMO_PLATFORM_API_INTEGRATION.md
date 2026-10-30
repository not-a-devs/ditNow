# TASK-DEMO-PLATFORM-API-INTEGRATION

- 상태: PARTIAL / TESTED (앱 팩터리 배선·격리 HTTP 회귀). Claude 작성 당시 실행은 NOT_RUN이며 아래 Codex의 실제 검증 결과와 구분한다. 메모리 데모를 MariaDB 영속 기능으로 표현하지 않는다.
- 소스 동결 목표 12:00 KST, 마감 12:30 KST (2026-10-30)

## 변경 파일

| 파일 | 내용 |
| --- | --- |
| `services/api/app/factory.py` | 공개 `data_provenance.router.router`, `build_travel_router(enabled=True)`를 `/api/v1`에 항상 mount. `settings.p0_runtime_enabled`가 참일 때만 기존 p0 router 다음에 `configure_demo_runtime(application)` 호출 |
| `services/api/app/integrations/demo_runtime.py` (신규) | 가상 데모 5개 모듈 연결 helper |
| `services/api/tests/test_demo_platform_integration.py` (신규) | 연결 계약 테스트 |

## Export / 계약

`app.integrations.demo_runtime`

- `API_PREFIX = "/api/v1"`
- `async demo_owner(ctx: Context) -> UUID` — `ctx.binding.principal.user_id`만 반환. `Context`는 기존 `platform_runtime.dependencies.get_context`(실제 token 세션 + 현재 승인 binding을 매 요청 재검증).
- `async demo_services_actor(owner=Depends(demo_owner)) -> DemoActor` — `DemoActor(user_id=owner)`.
- `configure_demo_runtime(application: FastAPI) -> None`
  - app 소유 메모리 저장소 5개(전역 아님): `state.demo_services=DemoServices()`, `state.demo_attendance=DemoAttendanceStore()`, `state.demo_profile=DemoProfileStore()`, `state.demo_action_center=DemoActionCenterStore()`, `state.demo_channels=DemoChannelsStore()`.
  - `dependency_overrides`: `demo_services.router.get_demo_actor → demo_services_actor`; `demo_attendance|demo_profile|demo_action_center|demo_channels.router.get_actor → demo_owner`. `get_context`/`get_runtime`은 override하지 않음.
  - 다섯 `router`를 `/api/v1` prefix로 include. 기존 p0 router는 변경 없음.
  - 모듈 import 실패 시 조용한 대체 없이 앱 생성 실패.

## 동작

- 기본(공개) 앱: 비공개 데모 저장소·라우트 없음(404), override 없음. 출처 안내·수동 이동 계산은 공개 동작.
- `p0_runtime_enabled=True`이나 runtime 미준비: 실제 `get_runtime`이 503 `UNAVAILABLE`. 호출자 header(`X-User-Id`, `X-Role` 등)·query·임의 bearer로 우회 불가.
- 식별자는 header/body/query/과거 세션 snapshot에서 읽지 않음. 새 identity·role·grant·DB 행·bootstrap 없음.
- 저장은 프로세스 메모리. 재시작 시 초기화, worker별 분리(기존 서비스는 1 worker). MariaDB 영속 아님.

## 가정 / 의존

- `demo_profile`, `demo_action_center`, `demo_channels`의 router/store는 검토된 별도 고유 커밋을 조합한 뒤 main에 병합된 PR96/97/98과 정상 동기화한다. 다른 작성자의 변경은 덮어쓰지 않는다.
- 세 모듈의 실제 경로·응답은 신규 HTTP 통합 테스트에서 현재 A/B context·무인증·위조 입력·타 소유자 작업 거부로 확인했다. fake context는 테스트 전용이며 실DB/실제 로그인 운영 검증이 아니다.
- 학교 정책은 새로 정의하지 않음.

## 2차 수정 (Codex 2PASS/5FAIL 대응)

- 원인: `from app.features.demo_attendance import router`(profile 동일)는 패키지 `__init__`이 재노출한 `APIRouter`를 반환 → `module.get_actor` AttributeError.
- `demo_runtime.py`: `DEMO_ROUTER_MODULES`에 하드코딩한 `app.features.demo_*.router` 경로를 `importlib.import_module`로 직접 로드(`demo_router_modules()`). 누락 시 시작 시 예외, silent fallback 없음. canonical `Context`/현재 소유자·503 fail-closed 의미 변경 없음. `factory.py` 1차 구현 그대로.
- 통합 테스트도 같은 submodule 경로로 import, 모듈명 일치 검사 추가.
- profile/channels/action-center 실제 라우트 A/B 소유 격리 테스트 추가(GET 자기 데이터 + PATCH/POST/DELETE/read, spoof header·body 필드 무시/400, 토큰 없음 401).

## 기존 테스트 충돌 해결 (TEST helper만 수정, 운영 라우트·오류 변경 없음)

- FastAPI의 lazy include 때문에 `app.router.routes[].path` 필터·개수 검사는 전역 router shadow를 제거하지 못했다. Codex가 세 helper를 bare `FastAPI()` + `SafeRequestMiddleware` + 기존 공통 exception handlers + 대상 feature router만 사용하는 격리 앱으로 기계 정정했다. 단언은 실제 OpenAPI 경로와 HTTP503/401·주입 catalog 동작으로 유지한다.
- 기본 앱의 승인된 공개 mount200은 신규 통합 테스트와 별도 기본 앱 테스트가 검증한다. 기존 feature의 비활성503·actor/catalog 주입 검증을 삭제하거나 완화하지 않았다.
- 신규 통합 테스트의 Depends 기본 인자 Ruff B008/포맷만 정정했으며 factory/공통 Context/업무 로직은 Codex가 변경하지 않았다.
- 승인된 공개3경로를 `test_foundation.py`/`test_openapi_export.py`의 정확 경로 집합에 추가하고 default OpenAPI와 신규 웹 타입을 기계 재생성한다. 이후 실제 CI에서 확인한 기존 사전프로토 보존 회귀를 위해 승인된 `mvp/src/shared/api/schema.d.ts` 한 파일도 기계 재생성한다. 사전 앱의 업무 코드·화면·상태·의존성은 변경하거나 신규 앱에 복사하지 않는다.

## 테스트 (NOT_RUN)

`services/api/tests/test_demo_platform_integration.py` — fake `get_context`는 테스트 전용이며 실제 DB 검증이 아님. `create_database_engine`을 monkeypatch로 차단해 engine/network 생성 없음을 확인.

1. 기본 앱: 공개 경로 존재, 비공개 데모 404·state 없음, 출처 200, 이동 계산 200 및 잘못된 입력 400, `Cache-Control: private, no-store`.
2. enabled+runtime 없음: 다섯 모듈 GET·services POST·attendance POST가 spoof header/query와 무관하게 503, override 대상 정확히 5개, 공개 경로 유지.
3. 모듈별 actor override가 현재 context의 A/B UUID로 해석, 토큰 없음 401.
4. demo-services·attendance A/B 소유 격리, 잘못된 코드 422, 캐시 헤더.
5. 같은 토큰의 binding 전환 시 이전 소유자 데이터 비노출, 철회 시 401.
6. 앱 인스턴스별 저장소 독립.
7. `demo_owner`가 binding principal만 반환.
8. 런타임이 바인딩하는 모듈이 실제 router submodule인지 확인.
9. profile·channels·action-center 실제 라우트 A/B 소유 격리.

## Codex 독립 검토·실제 검증 — 2026-10-30
- 업무 소스는 기존 공통 `Context`를 매 요청 해석해 내부 UUID만 주입한다. 새 신원/role/DB 권한을 만들지 않는다. 저장소는 앱 인스턴스별 메모리이며 재시작·다중 worker 공유/DB 지속성은 제공하지 않는다.
- 새 등록 5모듈의 실제 HTTP 경로를 A/B 현재 context로 호출해 본인 데이터 격리·타인 변경 거부·위조 header/body·무인증·철회·앱 인스턴스 분리를 검증했다. 이때 fake context override는 테스트에만 존재한다. 실제 로그인·원격 DB 검증은 NOT_RUN.
- shadow helper 정정 후 전용 통합/기존 travel/provenance **92 PASS**. 전체 API 1차 **1737 PASS / 2 FAIL**는 추가된 공개3경로의 옛 고정 목록 때문이었다. 승인된 공개 mount 사실에 맞춰 정확 목록만 갱신한 뒤 관련 **35 PASS**, 최종 전체 API **1739 PASS**(57.42초).
- 전체 Ruff check PASS, format **268파일 PASS**. 신규 통합 테스트의 B008과 포맷 초기 오류를 정정한 후 확인했다.
- `python -m app.export_openapi --check` 초기 stale 확인 → default snapshot 기계 재생성 → PASS. 신규 웹 OpenAPI 타입 생성/드리프트 검사·typecheck·build PASS. 최초에는 사전 mvp 생성 파일을 보존했으나 아래 실제 CI 증거에 따라 해당 생성 산출물만 정합을 맞춘다.
- 신규 웹 의존성은 `npm ci --offline --no-audit --no-fund`로 캐시만 설치했다. 검사에 실제 API/DB/학교/외부 모델 서버를 호출하지 않았다.
- 에이전트 탐색107경로·8스킬, 92 FR 진행표 오류0, `git diff --check` PASS. 기존 92개 요구사항 ID·인증/인가 정책·DB/migration·운영 비밀은 변경하지 않았다.
- 상태: PUBLIC 설명/순수 계산 mount와 P0 활성 설정의 메모리 demo 배선은 격리 HTTP에서 TESTED. 실제 브라우저/로그인·DEMO DB 원장·공개 HTTPS·운영 배포·학교 공식 업무는 이 PR에서 NOT_RUN. 메모리 데모에 DB 영속화 점수를 부여하는 근거로 사용하지 않는다.

## 실제 CI의 사전프로토 타입 회귀 정합 (범위 정정)
- 최초 PR HEAD f2ec776의 CI에서 Python·신규웹·Docker·MVP빌드·RAG는 PASS였으나 에이전트 설정 job의 마지막 `mvp npm run api:types:check`가 실패했다. 탐색 지도/92FR 검사는 PASS였다.
- `.github/workflows/python-api-ci.yml`의 실제 명령을 대조하여 기존 사전프로토 보존 회귀 타입 검사도 있음을 확인했다. '해당 검사가 없다'는 작업 중 추정을 정정하며, CI 재실행·검사 삭제로 덮지 않았다.
- root 승인 범위로 `mvp/src/shared/api/schema.d.ts` **한 생성 파일만** 기계 재생성했다. 기존 prototype 업무 코드·화면·상태·의존성 변경0, 신규 앱에 소스 재사용0.
- offline 설치 후 `npm run api:types`, `npm run api:types:check`, MVP `typecheck`, `build` 모두 직접 PASS. 최종 새 HEAD의 CI 전체 결과는 PR에 별도 기록한다.
