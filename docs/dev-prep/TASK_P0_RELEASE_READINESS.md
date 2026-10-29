# TASK-P0-RELEASE — 제출·배포 준비 상태 감사

확인일 2026-10-30 KST · 기준 HEAD `7f7eabb`(브랜치 `docs/p0-release-readiness-20261030`), 참고 `origin/main` `8c86132`. 성격: **읽기 전용 감사**. 변경 파일은 이 문서 1개이며 앱·설정·배포·CI·NAV·README·진행표 변경은 0이다. 배포·호스팅 활성화·팀원 메시지·유료 서비스·원격 DB 접속·LLM 호출을 하지 않았다. 비밀값·`.env`·DPAPI·클라우드 자격 증명·실제 개인 행을 읽지 않았다. `mvp/` 소스는 읽지 않았다(파일 이름 존재만 기록).

관련: [해커톤 게이트](../12_HACKATHON_GATE.md), [릴리스 범위](../09_RELEASE_SCOPE.md), [결정 기록](../11_DECISION_LOG.md), [적격성 기록](02_HACKATHON_ELIGIBILITY.md), [DB 연결 기록](07_DB_CONNECTIVITY_AND_ROLES.md), [92행 진행표](06_FEATURE_IMPLEMENTATION_STATUS.csv).

## 0. 판정 표기

| 표기 | 의미 |
|---|---|
| DEPLOYED | 실제 공개 URL에서 동작을 직접 확인함 |
| NOT_RUN | 확인 절차를 실행하지 않았거나 실행이 거부됨 |
| UNKNOWN | 저장소·허용된 조회 범위에서 판단할 근거 없음 |
| NEEDS_HUMAN | 사람의 정보 제공·결정·승인이 있어야 진행 가능 |

이 감사에서 **DEPLOYED 판정 항목은 0개**다. VERIFIED·실DB 완료를 주장하지 않는다.

## 1. 요약

1. **신규 제출 대상(`apps/web` + `services/api`)의 배포 흔적은 저장소 안에 없다.** 호스팅 설정 파일, 배포 워크플로, 공개 URL·도메인·HTTPS 설정, 운영 시작 명령(프로세스 관리자·리버스 프록시) 모두 미발견이다. 배포 여부 자체는 저장소 밖 근거가 없어 **UNKNOWN**이다(“배포 안 됨”의 증명이 아님).
2. README의 “배포는 진행 중입니다”는 진행 주장일 뿐 URL·환경이 기재되어 있지 않다. 근거 없음 → **UNKNOWN**.
3. GitHub의 deployments·environments·Pages·workflow 메타데이터 조회는 이 세션에서 `gh` 실행이 승인 화면 부재로 **자동 거부**되어 **NOT_RUN**이다. 조회되었더라도 GitHub 쪽 빈 결과나 404는 GitHub 밖 호스팅 부재의 증거가 아니다.
4. 제출 게이트 핵심(로그인·README 3 CRUD·2계정 격리)은 현재 main 기준 **서버에 마운트되지 않았다.** 로그인은 실서버 503(fail-closed), 업무 CRUD 라우터는 미마운트다. 배포가 있더라도 이 게이트는 현재 코드로 충족할 수 없다.
5. 적격성: **RESOLVED_USER_CONFIRMED** 유지. 사용자 확인은 있으나 공식 승인 문서는 저장소에서 확인되지 않는다(아래 §5). BLOCKED로 되돌리지 않는다.

## 2. 실제 실행한 확인과 결과

| # | 확인 | 방법 | 결과 |
|---|---|---|---|
| 1 | 필수 문서 | NAV/AGENTS/CLAUDE/10_AI_RUNBOOK/README/09/11/12/02/07, services/api·apps/web README, TASK_EXPLICIT_MARIADB_MIGRATION, TASK_DB_CRUD_VERIFICATION 읽기 | 읽음 |
| 2 | 호스팅 설정 파일 | Glob: Dockerfile, docker*, vercel.json, netlify.toml, render.yaml, fly.toml, Procfile, Caddyfile, nginx*.conf, *.service, wrangler.toml, railway.json, `.github/**` | `.github/workflows/` 4개, `chatbot/docker-compose.yml`, `mvp/vercel.json`만 발견 |
| 3 | 공개 호스팅 URL 문자열 | Grep(`mvp/` 제외): vercel.app, netlify.app, onrender.com, fly.dev, pages.dev, ts.net, github.io, railway.app | 공식 해커톤 안내 `skyman200.github.io/vibe/` 인용만 존재. 서비스 URL 0건 |
| 4 | CI 워크플로 내용 | `web-ci.yml`, `python-api-ci.yml` 읽기 | 둘 다 PR/push 검증(설치·타입·테스트·빌드·audit / ruff·pytest·OpenAPI)만. 배포 단계·environment·secrets 사용 없음 |
| 5 | API 마운트 경로 | `app/main.py`, `app/factory.py`, `app/api/v1/router.py` 읽기 | `/health`, `/api/v1/{health, discovery, ai, auth, public-campus}`만 포함. 업무 기능 라우터 미포함 |
| 6 | 92행 진행표 | CSV 파싱(Node, 따옴표 처리) | 92행: PARTIAL 66, NOT_IMPLEMENTED 21, BLOCKED 5. mariadb 열 NOT_RUN 91, N_A 1 |
| 7 | 비밀 예시 파일 존재 | Glob | `apps/web/.env.example`, `services/api/.env.example`, `chatbot/.env.example` 존재(내용 미열람) |
| 8 | `git log origin/main` | 로컬 원격 추적 참조 | 최신 `8c86132`. 배포 관련 커밋 없음(최근 8개 기준) |
| 9 | GitHub repo/deployments/environments/pages/workflows API | `gh api ...` 5건 | **NOT_RUN — 세션 권한 자동 거부**. 응답 미수신 |
| 10 | 공식 해커톤 페이지 재열람 | — | **NOT_RUN** (네트워크 조회 금지 범위). 저장소 기록의 2026-10-29 확인본만 인용 |
| 11 | 실제 URL HTTPS·health 접속 | — | **NOT_RUN** (대상 URL 없음, 원격 접속 금지) |

빌드·테스트는 이 감사 범위가 아니어서 실행하지 않았다(**NOT_RUN**). CI 성공을 이 문서에서 주장하지 않는다.

## 3. 배포 대상 식별

| 항목 | 신규 제출 대상 (`apps/web` + `services/api`) | standalone 챗봇 (`chatbot/`) | 제외 프로토타입 (`mvp/`) |
|---|---|---|---|
| 제출 대상 여부 | 대상 (DEC-018) | 통합 기능의 패키지 원본(DEC-017). 단독 실행은 개발·평가용 | **제외** (DEC-018) |
| 호스팅 대상/공급자 | **UNKNOWN** — 설정 없음 | 설정 없음. `docker-compose.yml`은 로컬 MariaDB(127.0.0.1:3306)만 정의, 앱 배포 아님 | `mvp/vercel.json` 파일 존재만 확인(내용 미열람). 제출 근거로 사용 금지 |
| 공개 URL·도메인 | **UNKNOWN** | 없음 | 해당 없음 |
| HTTPS/TLS(웹) | **UNKNOWN** | — | — |
| 빌드 명령 | `cd apps/web && npm ci && npm run build` → 정적 `dist/` (apps/web/package.json) | `uv sync --locked --all-extras` | — |
| 시작 명령 | 웹: 정적 호스팅 + `/app/*` SPA fallback 필요(apps/web/README). API: `uv run --locked uvicorn app.main:app --host … --port … --workers 1 --no-access-log` + 필수 `DIT_API_ENVIRONMENT`(services/api/README) | `uvicorn app.main:app` (개발용) | — |
| health | `/health`, `/api/v1/health` — 프로세스 생존만, DB·인증 준비 미검사 | — | — |
| 운영 서버 | **UNKNOWN**. 리버스 프록시·프로세스 관리자·로그 설정 문서 없음 | — | — |

**Tailscale 도달성:** 저장소 근거상 Tailscale은 **MariaDB 사설망(TCP 3307)** 용도다(DEC-019, 07 문서). 웹/API를 Tailscale serve/funnel 등으로 공개했다는 설정·기록은 없다 → **UNKNOWN**. 사설망 전용 주소는 심사위원 접속이 불가능하므로 그 자체로 “배포 URL”이 될 수 없다는 점만 사실로 적는다.

**배포 시 반드시 해결해야 하는 저장소 내 기록된 제약 (새 규칙 아님, 기존 문서 인용):**
- 요청 제한은 프로세스 메모리·단일 워커·`request.client.host` 기준이며 `X-Forwarded-For` 미신뢰 → 프록시 뒤에서는 모든 요청이 프록시 IP로 묶임. 신뢰 프록시 설정은 배포 전 게이트(services/api/README, PR28 F-05).
- CORS는 기본 비허용, `GET`/`POST`·`Content-Type`/`Authorization`만 허용(factory.py). 교차 출처로 배포하면 업무 모듈의 PATCH/DELETE/`Idempotency-Key` 허용 결정이 필요(TASK_COMMUNITY §68, TASK-K §136). 같은 출처 프록시면 불필요.
- 멱등 키 생성은 보안 컨텍스트(HTTPS) 필요(TASK-K §98) → 업무 쓰기 화면에는 HTTPS가 사실상 필수.
- `--no-access-log` 유지, 프록시 접근 로그의 URL/쿼리 기록 별도 검토(services/api/README).
- `LLM_PROVIDER=fake`는 `test` 외 환경에서 시작 거부, LLM 미설정 시 `/ai/ask` 503.

## 4. 제출 게이트 대조 (근거: 저장소 [12_HACKATHON_GATE](../12_HACKATHON_GATE.md), 공식 출처 https://skyman200.github.io/vibe/ 2026-10-29 확인본)

공식 페이지는 이번에 재열람하지 않았다(NOT_RUN). 아래 요구는 저장소에 이미 기록된 문구만 사용하며 새 규칙·승인을 추가하지 않는다. 일정 기록: 사전 점검 2026-10-30 11:00, 최종 제출 2026-10-30 13:30, `main` 최신 커밋 평가.

| 게이트 | 현재 근거 | 판정 |
|---|---|---|
| 공개 repo, 10/29 이후 커밋 | 02 문서: 공개·main, 첫 커밋 2026-10-29 10:44 KST. 생성일 2026-10-26 충돌은 사용자 해결 확인 | 사용자 확인 / 공식 증빙 NEEDS_HUMAN |
| 실제 배포 URL HTTPS·보호 화면·로그인 | URL 없음. 로그인 실서버 503 | **UNKNOWN(배포) / 로그인 미충족** |
| README 1·2·3 생성→목록→새로고침→수정→삭제 | 후보 FR-COM-001/004, FR-OPP-004: 모두 PARTIAL, mariadb NOT_RUN, 라우터 미마운트. OPEN-001(최종 선정) 미결정. CRUD 검사 도구는 rollback-only 오프라인 PASS만 | **NOT_RUN** |
| README 첫 3기능 = 3 DB CRUD 일치 | 현재 README 주요 기능 1~3은 AI 도우미·10개 메뉴·업무 모듈(“연결 전”)이라 CRUD 3시나리오와 불일치 | **미충족(문서)** — README는 root 소유 |
| 다른 계정/학과 차단, 익명 신원 비노출 | 모듈 단위 테스트(메모리 fake)만. 실서버 2계정 시험 없음 | **NOT_RUN** |
| 공지 원본→채팅 카드→학생 조회 | FR-NOT-001/002, FR-DEPT-* PARTIAL, 미마운트 | **NOT_RUN** |
| AI 데이터 기반·실패 처리·비용 제한 | `/ai/campus/search` 공개 검색 마운트. `/ai/ask`는 LLM 설정 필요, 개인 질문은 실서버 503. 분당 요청 제한(메모리) 존재. 비용 상한 공급자 설정 근거 없음 | 공개 검색 로컬 확인 기록만 / 배포 NOT_RUN / 비용 한도 UNKNOWN |
| 390/1280, Lighthouse 3회 | 로컬 Vite 390/1280 확인 기록(apps/web/README). Lighthouse 기록 없음 | 로컬 부분 / **Lighthouse NOT_RUN** |
| migration·인덱스·멱등성·오류 처리 | §6 참고. 앱 런타임은 16개 테이블을 사용하지 않음 | 부분 / 런타임 NOT_RUN |
| 심사용 계정 전달·권한 | 공통 신원 bridge 미병합, 실서버 로그인 503. OPEN-003 미결정 | **NEEDS_HUMAN** |
| 기본 브랜치 최종 커밋·README·.env.example | `.env.example` 3개 존재(내용 미열람). README 내용 불일치 위 참고 | 부분 |
| 팀원 조사·최종 제출 | 저장소 밖 행위 | **NEEDS_HUMAN** |

**개인정보·AI 출처·보안·TLS:** 학생·학적은 가상(DEMO) 데이터로 문서화되어 있다(DEC-020, README). AI 근거는 `chatbot/data/` 시설 스냅샷이며 출처 검증은 UNKNOWN으로 표시된다(services/api/README). 개인 응답 `Cache-Control: private, no-store`는 테스트 범위 기록만 있고 실제 프록시 캐시 검사는 NOT_RUN(PR39 문서). DB TLS1.3·CA·호스트 검증은 root 실서버 읽기 PASS 기록이 있으나(07 문서) **웹/API의 공개 HTTPS는 별개이며 UNKNOWN**이다.

## 5. 적격성 (사용자 해결 확인 vs 공식 증빙)

- 상태: [02 문서](02_HACKATHON_ELIGIBILITY.md)의 **RESOLVED_USER_CONFIRMED**를 그대로 유지한다. 재조사로 BLOCKED로 재분류하지 않는다.
- 사용자 확인: 있음(2026-10-29, 대화 내 명시).
- 공식 증빙: 운영진 서면 판단·「내 신청」 등록 내역·서비스 주소 등록 상태는 저장소에서 **확인되지 않음(NOT_VERIFIED)**. 등록된 서비스 주소가 무엇인지도 UNKNOWN이며, 그 주소가 신규 앱을 가리키는지 확인이 필요하다(NEEDS_HUMAN, 아래 §7 항목 2).

## 6. 92개 범위와 통합 수, DB 상태

- 92행 진행표: PARTIAL 66 / NOT_IMPLEMENTED 21 / BLOCKED 5. mariadb 열 NOT_RUN 91 / N_A 1. **실DB 검증 완료 행 0**.
- 통합 API에 실제 마운트된 기능: health, 공개 통합 검색(discovery), 공개 대학·학과 안내(public-campus), AI 공개 시설 검색, `/ai/ask`(LLM 설정 필요), auth(실서버 503). 신규 웹에 연결된 화면: 통합 홈·메뉴, `/app/ai` 시설 검색, `/app/information`, `/app/search`.
- 업무 모듈(커뮤니티·기회·학과·강의실·도서관·입학·생활·학사·홈 요약 등)은 `services/api/app/features/*`, `apps/web/src/features/*`에 부분 구현·테스트가 있으나 **전역 라우터·인증·UOW 미배선**이다. 화면 존재를 FR 완료로 집계하지 않는다.
- 원격 DB: 이번 작업 지시는 “원격 migration 16개 적용 완료 + legacy 9개 보존”을 현재 상태로 전달했다. 이 브랜치의 저장소 문서(07, TASK_EXPLICIT_MARIADB_MIGRATION)는 아직 적용 NOT_RUN으로 기록되어 있어 **root 보고로만 기록하고 이 감사에서 재현·확인하지 않았다**. 적용이 맞더라도 이는 스키마 존재 증거일 뿐 **배포된 앱이 그 테이블로 CRUD한다는 증거가 아니다**(앱 런타임은 16개 테이블 저장소를 라우터에 연결하지 않음).

## 7. 배포·심사 계정 진행에 필요한 최소 정보·승인 (NEEDS_HUMAN)

비밀번호·키·DSN은 이 목록에 적지 말고 승인된 비밀 경로로만 전달한다. 기존 호스팅 설정이 저장소에 없으므로 **새 유료 공급자 개설을 권고하지 않는다.**

1. **기존 배포 존재 여부와 위치**: 팀이 이미 운영 중인 웹/API 호스트가 있는지(공급자 또는 자체 서버 이름, 관리 담당자). 없으면 “없음”이라는 사실.
2. **「내 신청」에 등록된 서비스 주소**와 그 주소가 신규 `apps/web`을 가리키는지(mvp가 아닌지) 확인.
3. **공개 URL·도메인·HTTPS 종단 방식**: 인증서를 누가 어디서 종단하는지, 웹과 API를 같은 출처로 둘지(같은 출처 프록시 권장 근거: CORS/멱등 키 제약 §3).
4. **API 실행 위치와 DB 도달 경로**: API 호스트가 Tailscale 사설망의 MariaDB(3307)에 접근 가능한지와 그 연결 승인(OPEN-002). 공용 인터넷에 3307을 열지 않는다는 기존 원칙 유지.
5. **런타임 설정 주입 책임자**: `DIT_API_ENVIRONMENT`, `DIT_API_CORS_ORIGINS`, `DIT_API_DB_*`(ditnow_app만), LLM 설정 여부·공급자·월 비용 한도. migrator 자격은 런타임에 넣지 않음.
6. **배포 실행 승인**: 누가 언제 배포 명령을 실행하는지(AGENTS.md §9: 배포는 사람 승인). 이 감사 작업자는 실행하지 않는다.
7. **심사용 계정 절차(OPEN-003)**: 가상 계정 생성 책임자, 역할(학생 2 + 조교 1 등 09 문서 P0-A 기준) 승인, 전달 방식(제출 양식 필드 등). 비밀번호는 문서·PR·채팅에 남기지 않음. 현재 로그인은 공통 신원 bridge 승인 전 실서버 503이므로 **로그인 활성화 승인이 선행**된다.
8. **README 첫 3기능 확정(OPEN-001)**: DFLT-007 후보를 그대로 쓸지 팀 결정. README 수정은 root 소유.
9. **업무 라우터 활성화 순서 승인**: 인증 dependency·UOW·16개 테이블 저장소를 연결한 뒤 2계정·재시작 영속성 시험을 실서버에서 수행하는 일정.

## 8. 잔여 게이트

| 게이트 | 상태 |
|---|---|
| GitHub deployments/environments/Pages/workflow 메타데이터 | NOT_RUN(권한 거부) — 승인된 세션에서 읽기 전용 재조회 필요 |
| 공식 해커톤 페이지 최신본 재대조 | NOT_RUN |
| 배포 URL·HTTPS·health 실제 접속 | UNKNOWN / NOT_RUN |
| 로그인 활성화(공통 신원 bridge) | NEEDS_HUMAN |
| README 3 CRUD 실서버·2계정·새로고침 영속성 | NOT_RUN |
| 공지→채팅 카드 연결 | NOT_RUN |
| Lighthouse 모바일 3회 | NOT_RUN |
| 심사 계정 생성·전달 | NEEDS_HUMAN |
| 원격 migration 16 적용 상태 | root 보고만, 이 감사에서 미확인 |

## 9. 변경·증거 요약

- 변경 소스 0개, 변경 문서 1개(이 파일). NAV/README/공통 진행표 미수정(root 소유).
- 실행한 명령: §2 표의 읽기·Glob·Grep·`git log origin/main`·CSV 파싱. 거부된 명령: `gh api` 5건.
- 테스트·빌드·CI: 실행하지 않음(NOT_RUN). CI 통과를 주장하지 않는다.
