# TASK-DEPLOY-PREP — 현재 코드 기준 배포 준비와 승인 게이트

확인일: **2026-10-30 KST**. 기준 커밋: `f8705eac26dc12960b2689e894497e9893371ca5`. 상태: **DOCUMENTED / 실제 배포 NOT_RUN**. 이 작업은 문서 1개만 추가하며 호스팅·도메인·HTTPS 발급·비용·방화벽·시드·운영 설정을 변경하지 않는다. 원래 작업 트리의 조사 문서와 다른 작업자의 변경을 보존했다.

- 관련 결정: DEC-015~020. React/TypeScript/Vite/Tailwind, FastAPI/Pydantic/OpenAPI, MariaDB, 신규 `apps/web/`, 공통 신원 원장을 유지한다. 전체 92개 FR의 완료를 주장하지 않는다.
- 관련 요구사항: FR-AUTH-001/002, FR-COM-001/004, FR-OPP-004; NFR-SEC-001~007, NFR-PRIV-001/003, NFR-REL-001/003/004, NFR-OPS-001~004; TC-V1-AUTH-001/002, TC-V1-COM-001/004, TC-V1-OPP-004 및 390/1280 검증.
- 적용 스킬: `nav-doc-maintenance`, `quality-release-gate`. NAV·공유 문서는 root 소유이므로 이 작업에서 수정하지 않는다.
- 선행 조건: 배포 담당자·대상·접근 범위·비용·실행 계정·비밀 주입·롤백 책임자의 명시 승인. PR 코드 병합 승인은 이 조건들의 승인이 아니다.

## 1. 확인된 사실과 미확정 사항

| 항목 | 현재 근거와 범위 | 배포 판단 |
| --- | --- | --- |
| 실제 배포 대상·호스팅·도메인·공개 URL | 저장소 코드와 결정 대장에 최종 운영 대상 없음 | **미확정**. 공급자/유료 플랜을 선택하지 않음 |
| GitHub deployment/environment metadata | 읽기 전용 API 조회 결과 deployments `[]`, environments `total_count=0` | GitHub 등록 기록이 없다는 뜻. 다른 경로의 배포 부재까지 증명하지 않음 |
| 앱/API 구현 | [앱](../../apps/web/src/App.tsx), [공통 전송](../../apps/web/src/lib/api.ts), [API factory](../../services/api/app/factory.py) | 로그인·현재 신원·P0 CRUD 연결 코드 있음. 모의/SQLite 검증과 실DB E2E 구별 |
| 실제 DB 기반 | [root DB 실행 기록](07_DB_CONNECTIVITY_AND_ROLES.md), [병합 증거](TASK_PR_BATCH_MERGE_20261030.md) | root 기록상 엄격 TLS 및 16개 추가 DDL 적용, 기존 9개 정의/행 수 보존. 본 작업자 재접속 아님 |
| 실제 시연 계정·HTTP·브라우저 업무 검증 | 위 기준 커밋의 기록상 아직 NOT_RUN | 운영자가 이후 얻은 실행 증거를 별도로 갱신해야 함 |
| CI | `.github/workflows/`는 설치·타입·정적 검사·테스트·빌드·오프라인 하네스 검사 | 배포·공개 HTTPS·실DB CRUD·운영 비밀 사용 검사와 다름 |

GitHub metadata 조회는 `GET /repos/not-a-devs/ditNow/deployments`, `GET /repos/not-a-devs/ditNow/environments`만 사용했다. secret API·환경 값·DPAPI·실제 `.env`·DB 비밀번호·CA 파일 원문은 읽지 않았다.

## 2. 검토할 배치 구조 — 공급자 선택 전 설계 후보

```text
브라우저 HTTPS (승인할 단일 origin)
  ├─ /, /app/*       → apps/web/dist 정적 파일 + SPA fallback
  ├─ /assets/*       → 동일 release의 정적 자산, 없는 파일은 404
  └─ /api/v1/*       → FastAPI의 같은 /api/v1/* 경로 보존
                              └─ 사설 Tailscale 경로 → 기존 MariaDB
```

이 구조는 검토 후보이며 실제 프록시 설정 파일·배포 workflow는 아직 추가하지 않는다. 프런트 빌드는 [package.json](../../apps/web/package.json)의 `npm run build`이며 기본 산출물은 `apps/web/dist`다. 런타임은 이 경로만 정적 서비스하고 저장소·환경 파일·테스트 artifact를 웹 루트에 두지 않는다. `vite dev`/`vite preview`를 운영 정적 서버로 사용하지 않는다. [Vite 공식 안내](https://vite.dev/guide/static-deploy.html)(확인 2026-10-30).

### 경로와 HTTPS 수용 기준

1. `/app/login`, `/app/community`, `/app/recruitments`, `/app/opportunities`의 직접 진입·새로고침·뒤로가기를 검사한다. 현재 앱은 History API를 사용하므로 정적 서버 fallback이 필요하다.
2. `/api/v1/*`와 `/health`는 SPA fallback 대상에서 제외한다. API 404/405/503을 HTML 200으로 바꾸지 않는다. `/api/v1` prefix를 제거하거나 두 번 붙이지 않는다. 프록시가 별도 prefix를 추가한다면 `root_path`·OpenAPI·no-store·실제 URL 계약을 별도 검증한다.
3. 같은 origin이면 `VITE_API_BASE_URL`을 비워 `/api/v1`을 쓴다. 다른 origin이면 완전한 HTTPS API base를 **빌드 시** 주입하고 CORS도 맞춘다. 기존 번들을 옮긴 뒤 OS 환경만 바꿔 API 주소가 변경된다고 가정하지 않는다.
4. 실제 로그인은 HTTPS로만 노출한다. 토큰 전송은 현재 클라이언트가 HTTPS 또는 loopback HTTP만 허용하며, 로그인 UI도 비밀 전송의 안전한 목적지를 검사한다. 외부 HTTP를 시연 편의상 허용하지 않는다.
5. 인증·보호 요청에 redirect를 만들지 않는다. 프록시는 body/Authorization/If-Match/Idempotency-Key를 보존하고 다른 host로 전달하지 않아야 한다. 슬래시·HTTP→HTTPS 정규화는 비밀번호 입력 전 페이지 진입에서 처리하고 자격 요청을 3xx로 옮기지 않는다.
6. HTTPS 종료·인증서 갱신 주체·HSTS/CSP 등 응답 정책·만료 경보는 미확정이다. 공급자 선택 후 별도 검토한다. 브라우저 HTTPS와 DB TLS는 서로 다른 연결이다. [FastAPI HTTPS 설명](https://fastapi.tiangolo.com/deployment/https/)(확인 2026-10-30).

### 현재 CORS 값 — 코드 그대로

근거: [factory.py](../../services/api/app/factory.py), [Settings](../../services/api/app/core/config.py).

| 설정 | 현재 값 |
| --- | --- |
| origins | `DIT_API_CORS_ORIGINS`의 정확한 HTTP(S) origin 목록, 기본 `[]` |
| credentials | `False` |
| methods | `GET`, `POST`, `PUT`, `PATCH`, `DELETE` |
| request headers | `Content-Type`, `Authorization`, `If-Match`, `Idempotency-Key` |
| exposed response headers | `X-Request-ID`, `Idempotent-Replayed` |

origin에는 경로·userinfo·query·fragment·wildcard를 넣지 않는다. CORS middleware가 OPTIONS preflight를 처리하는 것과 업무 endpoint가 OPTIONS/HEAD를 지원하는 것은 다르다. CORS는 서버 인증/인가를 대신하지 않는다. 허용 origin의 실제 메서드·헤더 preflight, 금지 origin의 허용 헤더 부재, 실제 POST/PATCH/DELETE를 각각 확인한다. `VITE_*`는 공개 번들 값이며 비밀 저장소가 아니다.

## 3. 실행 artifact와 프로세스

### 재현할 빌드 — 실제 명령 예시, 이 문서 작업에서 실행하지 않음

```text
# 저장소 전체 배치를 보존한다. 위치는 배포 담당자가 정한다.
# services/api/pyproject.toml은 ../../chatbot 로컬 패키지에 의존한다.
# Python 3.13, uv 0.13.6
cd services/api
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
uv run --locked python -m app.export_openapi --check

# 별도 셸/작업 단계, 저장소 루트에서 apps/web로 이동
cd apps/web
npm ci
npm run api:types:check
npm run typecheck
npm test
npm run build
npm audit --omit=dev --audit-level=high
```

위 두 `cd` 블록은 각각 저장소 루트에서 시작하는 독립 단계다. API 디렉터리만 복사하면 로컬 `chatbot` 의존성 경로가 깨진다. Node는 package의 `>=22.12.0 <23 || >=24` 범위를 만족해야 하며 기존 CI 기준은 Node 22다. 운영 artifact에 dev 의존성을 제외하는 최적화는 잠금·패키징 회귀 검토 후 별도 결정한다. 자동 lock 재작성·새 프레임워크·컨테이너를 이 작업에서 도입하지 않는다.

### 승인 후 사용할 프로세스 예시

운영자가 배포 위치·설정·계정·네트워크를 먼저 검토하고 외부의 보호된 환경으로 설정을 주입해야 한다. 아래 loopback 명령은 공개 서비스 개설 명령이 아니다. 실제 기동은 **NOT_RUN**이다.

```powershell
# Windows: services/api/에서, 비밀은 셸 명령/argv에 기록하지 않고 별도 주입.
$env:DIT_API_ENVIRONMENT = 'production'
$env:DIT_API_DOCS_ENABLED = 'false'
uv run --locked uvicorn app.main:app --loop app.core.event_loop:new_event_loop --host 127.0.0.1 --port 8000 --workers 1 --no-access-log --no-proxy-headers
```

```sh
# Linux: services/api/에서, 승인된 설정을 process manager가 별도 주입.
DIT_API_ENVIRONMENT=production DIT_API_DOCS_ENABLED=false uv run --locked uvicorn app.main:app --loop asyncio --host 127.0.0.1 --port 8000 --workers 1 --no-access-log --no-proxy-headers
```

- [event_loop.py](../../services/api/app/core/event_loop.py)는 Windows에서 Selector, Unix에서 asyncio 기본 루프를 만든다. Windows의 aiomysql TLS 경로는 기존 진단에서 Selector 호환을 확인했다. Linux 실제 기동·DB 조합은 이 작업에서 검사하지 않았다.
- Windows Selector는 512 소켓과 pipe/subprocess 제한이 있다. 이 경로를 대규모 운영·다중 worker 호환의 증거로 사용하지 않는다. [Python 3.13 플랫폼 제한](https://docs.python.org/3.13/library/asyncio-platforms.html#windows), [Uvicorn custom loop](https://uvicorn.dev/concepts/event-loop/)(확인 2026-10-30).
- `--reload` 없이 **worker 1·프로세스/replica 1**을 초기 제약으로 유지한다. [Assistant](../../services/api/app/integrations/chatbot/assistant.py)의 IP별 limiter는 프로세스 메모리만 사용한다. 여러 worker/replica와 재시작은 제한 상태를 공유하지 않는다. 이 제약만으로 공개 서비스의 충분한 abuse 방어가 검증되지는 않는다.
- process manager·재시작·신호·graceful drain·메모리/동시성 상한·사용자 수·rolling update 방식은 미확정이다. 웹/DB 부하·중단 중 재전송·멱등성·잠금 테스트 후 수치를 정한다.

### 신뢰 프록시와 요청 제한

현재 `client_ip()`는 `request.client.host`를 사용한다. 프록시 뒤에서 아무 설정이 없으면 여러 사용자가 프록시 한 IP로 합산되거나, 잘못된 trust 설정이면 위조된 forwarded IP로 제한이 우회될 수 있다.

- 직접 로컬 실행 예시는 `--no-proxy-headers`로 환경의 암묵 trust를 쓰지 않는다.
- 실제 프록시 승인 후에는 정확한 연결 peer IP/네트워크만 `--forwarded-allow-ips`로 제한하고 `--proxy-headers`를 사용한다. `*`를 복사하지 않는다. 해당 peer만 API listener에 접근할 수 있는 네트워크 경계를 함께 확인한다.
- `Host`·forwarded proto·client IP를 프록시가 검증/재작성하고 외부 임의 `X-Forwarded-*`를 그대로 신뢰하지 않아야 한다. 사용자별 실제 IP·금지 peer·HTTPS redirect를 배포 환경에서 검사한다. 현재 앱에는 별도 TrustedHost/HTTPS 강제 middleware가 없으므로 외부 proxy 경계를 구현 완료로 가정하지 않는다.
- 기본 `DIT_API_ASK_RATE_LIMIT_PER_MIN=20`은 로그인·logout·`/auth/me`·AI ask가 공유한다. 정상 HTTP 검사기의 모의 transport 호출을 세면 **22개**다(login 4 / me 14 / logout 4). 같은 IP에서 1분 안에 돌리면 마지막 정리도 429가 될 수 있다. 실행 전 pacing/검사 전용 승인/제한 정책을 담당자가 검토해야 하며, 429를 PASS로 취급하거나 제한을 임의로 끄지 않는다.

관련 실행 옵션은 [Uvicorn settings](https://uvicorn.dev/settings/), proxy 의미는 [FastAPI behind a proxy](https://fastapi.tiangolo.com/advanced/behind-a-proxy/)를 확인했다(2026-10-30). 위 명령은 reverse proxy 제품이나 운영 trust 값을 확정하지 않는다.

## 4. 설정·비밀·DB 책임 원장

근거: [Settings](../../services/api/app/core/config.py), [엄격 DB factory](../../services/api/app/core/db_connection.py), [공통 runtime](../../services/api/app/integrations/platform_runtime/runtime.py), [승인 binding](../../services/api/app/integrations/platform_runtime/bindings.py).

| 설정/자료 | 실제 코드 동작 | 배포 전 담당자가 확인할 것 |
| --- | --- | --- |
| `DIT_API_ENVIRONMENT` | development/test/production 중 필수 | production이라는 이름만으로 TLS·P0·권한이 활성화되지 않음 |
| `DIT_API_LOG_LEVEL` | INFO/WARNING/ERROR, 기본 INFO | proxy/SDK/DB를 포함한 전체 로그 수집 정책 |
| `DIT_API_DOCS_ENABLED` | 기본 false, true일 때 `/docs`·`/openapi.json` | 운영 공개 여부와 접근 통제 별도 승인 |
| `DIT_API_P0_RUNTIME_ENABLED` | 기본 false, true일 때 P0 업무 router 등록 | 아래 gate가 부족하면 서비스는503, flag만으로 성공 아님 |
| `DIT_API_P0_SCHEMA_APPROVED` | 기본 false, 운영자 사전 검토 확인 | 실제 schema checksum·FK/CHECK/index·최소 GRANT·백업 증빙 |
| `DIT_API_P0_IDENTITY_APPROVAL_IDS` | 기본 빈 UUID 목록, 최대100개 | 검토된 감사 row UUID만 pin. 권한/계정을 생성하지 않음 |
| `DIT_API_DB_HOST/PORT/NAME/USER/PASSWORD` | HOST/USER/PASSWORD 전체 입력 필요. DB ditnow, 앱 ditnow_app, 포트 기본3307 | 승인된 사설 hostname/IPv4·SecretStr 비밀번호 외부 주입. 실제 값 출력/커밋 금지 |
| `DIT_API_DB_TLS_CA_FILE` | 존재하는 파일 경로. 없으면 시스템 CA 신뢰 사용 | 승인 CA 배포·접속 SAN 일치·파일 소유/권한·교체/만료 책임 |
| `DIT_API_DB_CONNECT_TIMEOUT` | 1~5초, 기본5초. TCP/TLS/auth 합산 연결 제한 | 전체 업무 SQL·pool 대기·request timeout을 모두 제한한 것은 아님 |
| `DIT_API_DATABASE_URL` | 통합 API에서 test의 정확한 in-memory SQLite 외 legacy 원격 경로 활성화 안 함 | 운영 연결 수단으로 사용하지 않음. 실제 DB는 엄격 `DIT_API_DB_*`만 |
| `DIT_API_LLM_PROVIDER/MODEL/API_KEY/BASE_URL/TIMEOUT_SEC` | provider 없으면 생성 기능503, 공개 시설 검색은 독립. fake는 test에서만 허용 | 공급자·모델·요금·데이터 전송·base URL·비밀/개인정보·timeout 승인 전 설정/호출 금지 |
| `VITE_API_BASE_URL` | 빌드 시 공개 API 주소 | 토큰·비밀번호·DB·LLM 키 절대 금지 |
| migrator 자격·DDL 원장·DEMO 비밀번호 | 별도 운영 명령만 사용 | 앱/브라우저/CI 기본 환경에 넣지 않음. 보호 위치와 접근 책임자 지정 |

### DB 경계

1. 기존 MariaDB에만 승인된 Tailscale 사설 경로로 접근한다. 개발 PC에 중복 DB를 만들거나 DB 포트를 공용 인터넷에 열지 않는다. 배포 대상이 해당 tailnet/ACL에 접근할 수 있다는 증거는 아직 없으므로 **대상별 NOT_RUN**이다.
2. factory는 `CERT_REQUIRED`·`check_hostname=True`·서버 TLS capability를 인증 전에 요구한다. `local_infile=False`, autocommit/echo 비활성, credential 없는 engine URL, `hide_parameters=True`, `utf8mb4_unicode_ci` 연결 초기화를 유지한다. TLS 미지원 fallback을 막는 aiomysql private hook이 있어 드라이버 변경 시 전용 회귀가 필요하다.
3. **CA 지문 pin 검사는 운영자의 사전 확인이다.** 현재 factory는 전달된 CA 신뢰/호스트 검증을 수행하며 기대 DER SHA-256 상수를 자동 비교하지 않는다. 승인된 CA 원본·지문·SAN·교체 절차는 [root 기록](07_DB_CONNECTIVITY_AND_ROLES.md)에서 대조한다. 인증서 검증을 끄거나 IP/SAN 불일치를 무시하지 않는다.
4. 앱은 `ditnow_app`만 사용하며 실제 GRANT는 운영자가 별도 확인한다. `ditnow_migrator`·DDL 원장 쓰기는 승인된 별도 프로세스에서만 수행한다. startup `create_all`·자동 migration·자동 시드·권한 부여가 없다.
5. 이미 적용한 16개를 “빈 DB 초기화”로 다시 적용하지 않는다. 기존9+신규16과 적용 장부/checksum을 조사한 뒤 필요한 추가 변경만 리뷰한다. MariaDB DDL을 애플리케이션 트랜잭션 rollback으로 취소할 수 있다고 가정하지 않는다.
6. 신원은 승인된 legacy 학번 세션→정확한 issuer/subject→공통 UUID 매핑과 현재 identity/profile/membership/role 검증을 따른다. 기존 학생 전체를 DEMO로 바꾸거나 이름/학년/해시로 자동 매칭하지 않는다. 로그인·관리자·실사용자 시드는 이 문서로 승인하지 않는다.

## 5. liveness와 readiness

| 검사 | 실제 구현 | 해석 |
| --- | --- | --- |
| `/health`, `/api/v1/health` | DB/auth를 검사하지 않는 성공 envelope의 `data: {status: 'ok', service: 'ditnow-api'}` | 프로세스 생존만. DB 장애에도200일 수 있음 |
| `PlatformRuntime.ensure_ready()` | 첫 사용에 MariaDB11.4/연결 collation/DB명/필수 테이블·컬럼 검사 후 프로세스 내 cache | 지속 readiness endpoint가 아님. FK/CHECK/GRANT·버전 장부·업무 권한·상시DB건강까지 증명하지 않음 |
| `python -m app.db.live_check` | 명시 opt-in일 때만 DB metadata 조회 | 운영자 별도 실행. 기본 NOT_RUN, public readiness로 공개하지 않음 |
| `/auth/me` | 현재 token·승인 binding·소속/역할 재검사 | 승인된 계정의 기능 probe. unauth는401 또는 미설정503이며 health와 다름 |

현재 `/ready` endpoint는 없다. 로드밸런서에는 health만을 업무 준비로 사용하지 않고, 별도 준비 검사·최초 트래픽 허용·DB 장애 후 제외 정책을 설계해야 한다. 이 문서에서 새 endpoint나 권한 우회 probe를 구현하지 않는다. DB가 끊겼을 때 안전한503, 재연결·복구 후 재조회, 오래된 승인/역할의 거부를 각각 확인해야 한다.

## 6. 로그·관측과 비밀 보호

- [SafeRequestMiddleware](../../services/api/app/core/logging.py)는 서버 생성 request ID·고정 event·method·status를 남기며 URL/query/body/header·예외 원문을 기록하지 않는다. Uvicorn access log는 끄고 proxy·CDN·hosting·LLM SDK의 별도 로그도 검토한다.
- auth·익명/모집·개인 저장·기회·AI ask 경로의 `private, no-store`를 proxy가 제거/덮어쓰거나 CDN 캐시하지 않게 한다. 오류·404·redirect도 검사한다. 토큰·비밀번호·익명 private author·개인 응답이 로그·브라우저 cache·referrer에 남지 않아야 한다.
- 운영 경보의 최소 후보는 프로세스 중단·503/500/429 증가·CA 만료/검증 실패·DB 연결 실패·정리 실패다. 현재 앱 로그에는 latency/route 집계가 없으므로 이미 관측 가능하다고 주장하지 않는다. 관측 제품·보존기간·개인정보 접근·비용은 미확정이다.
- 셸 transcript·CI output·설정 dump·screenshots/HAR/trace가 비밀을 저장하지 않게 한다. 검증 도구는 default NOT_RUN과 안전 출력 경계를 유지한다. 실제 보고서는 저장소 밖 보호 위치에 보관하고 공개 PR에는 마스킹한 범위/개수만 남긴다.

## 7. 출시 전 smoke와 되돌리기 — 아직 실제 실행하지 않은 수용 기준

| 순서 | 담당·선행 | 통과 조건 / 미통과 시 |
| --- | --- | --- |
| 1 | 사람: hosting/domain/비용/접근 범위 승인 | 공급자·지역·운영자·정적/API 대상·HTTPS·tailnet 경로·비밀 주입 책임 확정. 미확정이면 공개 배포 차단 |
| 2 | QA: 최종 release SHA 고정 | 같은 SHA의 필수 CI·agent/92개 추적·API OpenAPI·신규 FE 타입/build·하네스 단위 검사. 이전 HEAD 성공으로 대체하지 않음 |
| 3 | 운영자: 제한된 기동 | reload 없는 1프로세스, private bind/proxy trust·환경 검증·기동/종료·비밀 로그 부재. health와 업무 준비 구별 |
| 4 | 운영자: 승인된 DEMO 준비 | 사전 스키마·CA·GRANT·감사 pin 대조. 명시 계정 CLI 기본 dry-run 후 별도 apply 승인. 기존 충돌은 자동 채택/리셋 금지 |
| 5 | root: 실제 localhost HTTP 검사 | [HTTP 검사기](TASK_P0_SECURITY_E2E.md)로 2계정 로그인/me·익명/모집/개인 준비 CRUD·B의 타 소유자 변경 거부·CAS/멱등·logout/relogin·토큰 폐기·정리 확인. rate budget 먼저 해결 |
| 6 | root: 실제 브라우저 | [하네스](TASK_P0_BROWSER_E2E.md)로 390/1280·현재 로그인·실CRUD·실패/재시도·이전 응답 폐기·logout. 현재 하네스는 loopback만 허용하므로 공개 URL을 억지로 주입하지 않음 |
| 7 | 운영자: 실제 ingress smoke | 승인된 URL에서 SPA 직접 진입·API JSON 404·HTTPS·금지 origin·CORS 메서드/헤더·proxy client IP·비밀/익명/no-store 확인. localhost 하네스 통과만으로 공개 환경 완료를 표시하지 않음 |
| 8 | 운영자: 지속성·복구 | 승인된 자기 표본만 재로그인·프로세스 재시작 후 재조회. 동시 연결 CAS/정원/잠금·DB 장애 복구·백업 복원. 단위 SQLite/refresh만으로 완료 처리 금지 |
| 9 | 사람: 공개·제출 승인 | 모든 NOT_RUN/잔여 문제·시연 기능/미활성 범위·DB/LLM 비용·긴급 중지/연락책·롤백 승인 확인 |

### rollback 순서 후보

1. 현재 release SHA·정적 artifact·잠금 파일·설정 버전 참조와 이전 검증 release를 기록한다. 비밀값은 artifact에 넣지 않는다. FE/API를 호환되는 한 쌍으로 관리하고 정적 HTML과 hashed assets가 서로 다른 release로 섞이지 않게 한다.
2. 민감 노출·권한 실패·업무 데이터 손상 위험이면 새 트래픽/해당 기능을 먼저 중지한다. `DIT_API_P0_RUNTIME_ENABLED=false` 재기동은 업무 router를 비활성화하는 선택지이나 기존 DB 세션을 자동 철회하는 기능은 아니다. 기존 토큰 폐기·키 회전은 별도 검토한 운영 절차로 처리한다.
3. 이전 artifact로 되돌리기 전에 새 DB 스키마와의 호환을 확인한다. 앱 rollback을 이유로 16개 테이블 DROP·행 삭제·백업 덮어쓰기·사전 `mvp/` 복귀를 하지 않는다. 데이터 복원은 백업·복구 책임자와 별도 승인이 필요하다.
4. 되돌린 SHA에서 health·업무 준비·2계정 거부·기존 표본 재조회·logout을 재검사한다. RPO/RTO/허용 중단·보존 수치는 아직 미확정(OPEN-R14)이며 복구 시험도 NOT_RUN이다.

## 8. 오래된 문서와 수정 제안 — 이 작업은 타 파일을 고치지 않음

| 경로/표현 | 현재 코드와의 차이 | 후속 제안 |
| --- | --- | --- |
| [API README](../../services/api/README.md)의 “DB 어댑터가 없음/비연결·미마운트/학생 CRUD 없음/승인 대기” 문단 | 공통 runtime·조건부 P0 router·me·실제 DB 적용 기록은 이미 main에 있음 | 당시 기반 설명은 역사로 표시하고 현재 flag/원장 경계·실E2E NOT_RUN을 별도 갱신 |
| [웹 README](../../apps/web/README.md)의 “로그인·세션 없음/업무는 안내화면/공개타입만” | 단일 메모리 로그인·실제 API 전송·P0 연결 코드 있음 | [LIVE WEB](TASK_P0_LIVE_WEB.md) 기준으로 코드·모의 검증·실브라우저 미검증을 구분 |
| [루트 README](../../README.md)의 DATABASE_URL·독립 챗봇 로그인·`.env` 예시 | standalone 개발/평가와 통합 운영 경로가 다름. services/api는 dotenv 자동 로딩 없음/legacy 원격 URL 차단/fake는 test 전용 | 운영 복사 금지 안내와 통합 DIT_API_DB/승인 gate 예시를 별도 검토. 기존 평가 수치가 새 배포의 증거는 아님 |
| [초기 준비 감사](01_READINESS_REVIEW.md)의 mvp 중심 구조·Supabase/PostgreSQL 후보·과거 취약점 | 후속 DEC-015~020과 신규 코드/의존성 PR이 우선 | 원래 감사일자 유지, 현재 기술·취약점·실행 증거는 후속 문서로 연결 |
| [API .env.example](../../services/api/.env.example) | 현재 DB 설명은 있으나 P0 승인 flag·audit pin·LLM 옵션은 누락 | 비밀 없는 키 목록 보완은 설정 owner 별도 PR. 이 문서의 키가 운영값/승인 증거가 아님 |
| [출시 범위](../09_RELEASE_SCOPE.md)의 학생3/조교1 시드 제안 | 현재 검토된 CLI는 학생2+비활성 감사 actor만, 교수/조교/admin 생성0 | 시연 권한 승인/실제 추가 코드·검증 전 역할 존재 주장 금지 |

## 9. 이번 작업의 검증 기록

- 수행: 위 로컬 코드·README·예시·release/DB/통합 기록 읽기, 공식 Uvicorn/FastAPI/Vite/Python 문서 확인, GitHub deployment/environment **metadata만** 읽기.
- 수행: 기존 HTTP checker의 `MockTransport` 정상 경로 오프라인 실행1회로 auth 요청22개 확인. 비밀번호는 테스트 내부 합성값이며 실제 네트워크/credential 파일/DB를 사용하지 않았다. 이 결과는 요청량 산정이며 실제 인증 통과가 아니다.
- 실제 문서 검사: 로컬 상대 링크 **25개 존재**, `node scripts/check-agent-config.mjs` **PASS**(현재 경로100/skill8쌍), `node scripts/check-feature-progress.mjs` **PASS**(92행, 66 PARTIAL/21 NOT_IMPLEMENTED/5 BLOCKED/0 IMPLEMENTED), `git diff --check` **PASS**.
- 수용 기준: 소유한 Markdown 1개만 변경, 모든 로컬 링크 실재, agent/92개 진행표/diff 검사와 PR 새 HEAD CI 확인. 새 코드·migration·비밀·배포 설정0.
- **NOT_RUN**: 실제 공개/사설 서비스 기동·HTTP·브라우저·DB·CA/비밀 파일 조회·새 계정 생성·비용 발생·도메인/DNS/방화벽 변경·배포·Linux 운영 부하·실제 백업 복원·출시 승인.
- 독립 리뷰·PR CI 결과는 PR에 기록한다. 문서 작성/CI 성공만으로 DEPLOYED·전체 VERIFIED 또는 사람 승인으로 표시하지 않는다.
