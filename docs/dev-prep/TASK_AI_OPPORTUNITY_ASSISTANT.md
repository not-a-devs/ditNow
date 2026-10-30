# TASK-AI-OPP-01 — 기회 탐색부터 확인 저장까지

2026-10-30 KST. 사용자가 사전 분석을 승인하고 기존 DEMO·strict TLS·공통 로그인으로 1차 수직 구현과 실제 검증을 지시했다. 원래 가상 원장 승인 `DITNOW-P0-DEMO-20261030`의 계정·감사 pin 두 개를 재사용한다. 새 계정·시드·DDL·외부 모델 호출·운영 배포는 실행하지 않는다.

관련 FR: FR-AUTH-001/002, FR-OPP-002/004, FR-AI-002/003의 **규칙 부분**. NFR-SEC-001/002/004~006, NFR-PRIV-002/003, NFR-AI-001~004, NFR-DATA-002/003, NFR-REL/UX. TC-V1-OPP-002/004, TC-V1-AI-002/003의 부분 범위, TC-012/018. 92개 기능 ID를 유지하며 개인 행동 브리핑 전체·LLM 추천 완료를 주장하지 않는다.

## 구현과 소유권

| 담당 | 격리 worktree/브랜치 | 파일·역할 | PR |
|---|---|---|---|
| A | `ditNow-ai-opportunity-api` / `feat/ai-opportunity-api-20261030` | P0 transport·동일 UOW matching·현재 학적 SQL reader·회귀 | [75](https://github.com/not-a-devs/ditNow/pull/75) |
| B | `ditNow-ai-opportunity-web` / `feat/ai-opportunity-web-20261030` | 추천·초안 편집/선택·명시 확인·부분 저장/재조회 | [77](https://github.com/not-a-devs/ditNow/pull/77) |
| C | `ditNow-ai-opportunity-e2e` / `test/ai-opportunity-e2e-20261030` | 독립 QA·AI 전용 opt-in 브라우저 하네스 | [78](https://github.com/not-a-devs/ditNow/pull/78) |
| root | `ditNow-ai-opportunity-flow` / `feat/ai-opportunity-flow-20261030` | 공통 전송/App·취소 인자·계약·실제 비밀/DB/로컬 실행·문서·통합 | 통합 PR에서 연결 |

인증 원장·권한 정책·schema/migration은 변경하지 않는다. 모집 추천 참조는 미연결 `NOT_CONNECTED`를 유지한다. A/B/C는 비밀·실DB에 접근하지 않았으며 root만 승인된 로컬 실행을 수행한다. 독립 Codex 검토는 사람 승인이 아니다.

## 연결한 계약

- `GET /api/v1/me/opportunity-matches`: 기존 관심 분류/키워드·페이지 계약과 MatchPage 재사용.
- `GET /api/v1/me/opportunity-matches/{id}/brief`: 원문·추천 근거·준비 절차·주의 사항 재사용.
- 공통 토큰→검토된 identity→현재 단일 active DEMO 소속·학생 역할→공통 SQL catalog를 **같은 저장소 트랜잭션에서 다시 검증**한다. 요청의 학과·학년·다른 사용자 ID를 신뢰하지 않는다. 긍정 정수 학년을 사용하되 학교 상한을 새로 만들지 않는다.
- 주관기관 빈 원본을 DB에서 변경하지 않고 웹에서 `미확인`으로 표시한다. DEMO·미확인 출처·자격 보장 아님·마감/기간을 구분한다.
- 신규 `/app/ai`는 공통 로그인 후 기회 탐색을 제공하며 기존 공개 시설 검색을 보존한다. 질문 입력은 명시한 관심 키워드로 규칙 매칭하며 자연어를 이해한 LLM 결과라고 표시하지 않는다.
- 초안은 브라우저 메모리에만 둔다. 검토→선택 항목 명시 동의 뒤에만 기존 `PUT /me/saved-opportunities/{id}`, 체크 POST를 사용한다. 성공 후 서버 재조회로 항목을 확인하고 내 준비 목록으로 이동할 수 있다.
- 기존 기록·메모·상태는 보존한다. 체크별 멱등 키를 유지하고 부분 성공을 전체 성공으로 표시하지 않는다. 이전 PUT 후 기록이 사라지면 자동 재생성하지 않는다. 공고·현재 소속이 변하면 재검토하며 계정 전환/언마운트·401/403 시 이전 초안·응답·후속 쓰기를 폐기한다.

## 현재 DEMO 읽기 전용 확인

strict CA 지문·체인·호스트 검증, MariaDB11.4.13·TLS1.3·app계정·25테이블·필수 schema를 확인했다. 지속 쓰기/DDL 0. 초기 래퍼에서 필수 environment 누락으로 연결 전에 실패했고 설정 후 재검사에 통과했다.

공개 후보는 기존 승인된 **학교 전체 contest DEMO 1건**이다. 지원 조건은 있으나 주관기관·원문 URL·마감·원문 확인일은 없다. 따라서 저장 동선·본인 소속 컨텍스트·미확인 표시를 시연할 수 있지만 학과별 후보 차이/실제 마감 임박 순위는 이 데이터로 검증할 수 없다. 학교 공식 공고를 발명하거나 원본 행을 수정하지 않았다. 데이터 확대는 오늘 우선순위에서 뒤로 미루며 필요 시 별도 승인을 받는다.

## LLM 2차 준비 — 호출 없음

`services/api/app/features/opportunity_matching/planning_contract.py`의 Pydantic 계약만 준비했다.

- 입력은 공개 기회 ID·source_kind·원문 근거 필드만 허용한다. 학과·학년 일치 여부를 추론할 수 있는 규칙 코드도 제거했다. 학번·사용자 UUID·이름·토큰·학과/학년 값·질문·관심어·개인 메모/체크/성적/상담은 입력에 없다.
- 출력은 요약·준비 항목·이유·원문 근거 ref뿐이다. 기회 ID 및 근거 ref를 원본과 대조하고 extra 필드·URL/도구 실행 payload·자격 보장/확인 생략을 거부한다.
- 이것은 문장의 사실성을 완전히 보증하지 않는다. 공고 원문은 비신뢰 데이터이며 2차에서 injection·서버 검증·사용자 확인·시간/횟수/비용·취소 검사를 추가해야 한다.
- 외부 공급자/모델·예산 상한·전송 필드·실호출 승인 전 LLM 실행은 NOT_RUN이다. 실제 provider 설정값/비밀을 열람하거나 유료 호출하지 않았다.

## 실제 검사 — 실행 범위별 결과

| 검사 | 결과와 범위 |
|---|---|
| API 전체 | 1515 PASS (11:10 실행), 기존 Starlette deprecation 경고1. Ruff·format237·OpenAPI snapshot 일치 |
| A 전용 | 53 PASS + 최상위 오류 본문 정정 10 PASS |
| 향후 LLM 계약 | 오프라인15 PASS, 실제 모델0. 독립 Claude 지적 후 개인 매칭 신호 제거 |
| B 웹 | 최종 전용46 PASS, 동일HEAD CI 전체554 PASS |
| 통합 App·전송·초안 | 최종 웹 전체561 PASS·type/build PASS (2026-10-30 11:10 KST). 이전 공개390/1280 메뉴·제목·포커스 검사 PASS |
| C 하네스 | 최종 오프라인64 PASS, 모의 결과를 실제DB로 표시하지 않음 |
| 통합 실제 HTTP | PASS_HTTP_SCOPE: 로그인·기존3CRUD·B차단·동일키/revision·logout/relogin·API 정리 확인 |
| 기존 P0 브라우저390/1280 | PASS: 21단계, 10:20~10:22 KST. 캡처된18토큰 폐기 확인 |
| 새 기회 확인저장390/1280 | PASS: 실행 코드 eebc1b42ef1fae7d97e53035378427943571b9f6, 10:38:52~10:40:02 KST, 사전3+각화면7단계=17단계. 확인 전쓰기0·편집/저장/재로그인·B조회/변경차단·본인API정리. 캡처10토큰 폐기 |
| 실패 실행 이력 | 첫 실행은 메뉴 accessible name, 두 번째는 textarea label 선택자 실패. 각각 FAIL이며 성공으로 덮지 않는다. 하네스 수정·회귀 후 세 번째가 PASS |
| 사후 DB 정합성 | INCOMPLETE: saved/check0 및 테스트 리소스 정리는 확인. 전역 세션 수 기대값 검사 FAIL, 가상 A의 미귀속 세션1 보존. 만료시각과 기존12시간 TTL로 추정한 발급시각은 이번 서버 시작 이전이나 출처 확정은 아님. 캡처 토큰 폐기 성공과 전체 세션0을 구분 |
| 운영 배포·외부 공개·LLM | NOT_RUN |

실행 서버는 loopback 한정 단일 worker, 검토된 감사 pin2·strict TLS, 분당1000 요청은 기존 승인된 격리 로컬 검증 설정뿐이다. 비밀번호·토큰·개별 UUID·원문 로그는 저장소 밖 DPAPI/보호 기록에 두고 문서·PR로 옮기지 않는다. 확인되지 않은 commit을 재생하는 자동 재시도나 DB 직접 삭제로 테스트 결과를 숨기지 않는다.

## 병렬 독립 리뷰

Codex A/B/C는 격리 브랜치에서 API·UI·하네스를 교차 검토했다. Claude Code CLI의 기존 승인된 읽기 전용 세션 6개도 완료했다. `Read/Grep/Glob`만 허용했으며 코드 쓰기·셸·커밋·비밀 접근 권한은 주지 않았다. 이는 사람 승인이나 제품 LLM 실행이 아니다.

- 반영: 향후 LLM 입력의 학과/학년 매칭 규칙 신호 제거. 공개 공고 근거만 투영하고 단위15건으로 검증.
- 미채택: 부분 성공 화면의 닫기 버튼 위험 지적은 현재 코드에 해당 버튼/경로가 없어 재현되지 않았다. 같은 멱등 키로 재시도하는 보호를 유지했다.
- 후속: 저장 목록 N+1 조회와 공유 행 잠금의 처리량은 측정이 필요하다. 정합성 잠금을 급히 제거하지 않았다. 공개 텍스트 내 연락처·프롬프트 주입·생성 문장 사실성은 실제 LLM 도입 전 별도 검증 대상이다.
- 한계: Claude의 92행 감사 세션은 앞72행만 읽었다. 전체92개 독립 감사 완료로 표시하지 않는다. 일부 배포 리뷰는 새 Docker 패키지 이전 SHA 기준이다.

## 후속 게이트

새 브라우저 단계의 PASS/FAIL/INCOMPLETE/NOT_RUN, 세션 폐기와 marker·소유권 기반 API 정리, 같은 통합 HEAD CI와 독립 리뷰를 기록한다. [모의 심사](../judging/SCORECARD.md)는 main 병합과 CI 뒤 갱신하고 실제 모델 점수는 규칙 구현으로 올리지 않는다.
