# TASK-A — P0 서버 계약 독립 설계 검토와 보완

확인일: 2026-10-29. 상태: **DOCUMENTED / 보안 계약 변경 사람 승인 대기**. 검토 대상은 [PR #11](https://github.com/not-a-devs/ditNow/pull/11)의 HEAD `219aff5377a6652db5f1797ac743c7880feeadd0`이며, 사용자가 병합한 main `5d08cb4d4cd92ea06dbe5404b69e894eb0a0822a`에서 후속 보완을 분리했다.

추가 Claude 리뷰 확인·후속 보완일: **2026-10-30 KST**. 10월 29일의 원 설계와 Codex 검토 기록은 위와 같이 보존한다.

## 최신 사용자 결정과 현재 계약

2026-10-30 사용자가 DB를 **MariaDB로 확정**했다. 클라우드 인스턴스는 예정이며 접속정보·버전·계정 권한·비용 조건은 아직 없다. DB 제품 선택에 대한 차단은 해제하고 인증 공급자·공통 세션, 가상 권한 생성 책임자, 클라우드 접속/관리 권한·비용·보존 게이트는 유지한다. 아래 Codex/Claude 원 리뷰의 PostgreSQL/RLS 설명은 당시 원 HEAD의 **역사적 맥락**이며 최신 MariaDB 준수 기준이 아니다.

chatbot은 하나의 DIT NOW 플랫폼 내부 기능으로 사용자·로그인 세션·학적 원장을 공유한다. 최종 통합은 services/api 중심이며 standalone 로그인은 대체한다. 사용자 결정에 따라 mvp는 사전 프로토타입으로 격리하고 최종 시연·제출·소스 복사에 사용하지 않는다. apps/web의 프런트는 신규 작성한다. 과거 MVP 코드 확인이나 CI 결과를 최종 구현 증거로 사용하지 않는다.

현재 계약은 FastAPI 인가·소유권/부모 범위 질의·MariaDB 최소 GRANT를 요구하고 제한 view/루틴·계정 분리를 후보로 남긴다. PostgreSQL의 auth.uid/SET LOCAL/BYPASSRLS·행 정책은 전제하지 않는다. 공식 지원 확인(2026-10-30): [MariaDB GRANT](https://mariadb.com/docs/server/reference/sql-statements/account-management-sql-statements/grant)는 테이블/컬럼/루틴 권한, [CREATE VIEW](https://mariadb.com/docs/server/server-usage/views/create-view)는 DEFINER/INVOKER 권한 문맥, [CREATE FUNCTION](https://mariadb.com/docs/server/reference/sql-statements/data-definition/create/create-function)은 루틴 권한 문맥과 EXECUTE 권한을 설명한다. 이 지원 사실이 앱 사용자 신원이나 자원 소유권을 자동 증명하지는 않는다. 실제 클라우드의 기능·물리 타입·운영 권한은 NOT_RUN/미확인이다.

## 검토 주체와 범위

초기 설계 작성 에이전트와 별도의 **Codex 리뷰 에이전트**가 PR #11의 전체 변경 파일 15개, 관련 FRD/NFR/RBAC와 현재 브라우저 모의 API를 읽기 전용으로 검토했다. 이후 사용자의 명시 요청으로 **실제 Claude Code CLI**의 추가 독립 리뷰를 수행했고 아래에 별도로 기록했다. 둘 다 AI 설계 리뷰이며 사람의 보안 승인으로 간주하지 않는다. Codex 리뷰 당시 GitHub 리뷰·댓글은 0건, 해당 HEAD의 MVP CI는 SUCCESS였다. 이후 PR #11의 사용자 병합은 과거 사실이며 이 후속 변경의 승인까지 뜻하지 않는다.

검토 기준: [프로젝트 지침](../../AGENTS.md), [보안 리뷰 스킬](../../.agents/skills/rbac-privacy-review/SKILL.md), [명세 비교 스킬](../../.agents/skills/spec-gap-review/SKILL.md), [DEC-015](../11_DECISION_LOG.md), [P0 계약](../v1-draft/13_P0_SERVER_DB_RLS_CONTRACT.md). 관련 ID는 FR-AUTH-001/002, FR-COM-001/004/005, FR-OPP-004, NFR-SEC-001/002, NFR-PRIV-001, NFR-REL-003, TC-V1-AUTH-001/002, TC-V1-COM-001/004/005, TC-V1-OPP-004다.

## 발견 사항과 문서 수정

| 검토 ID·심각도 | 원 HEAD의 근거 | 수정한 계약 | 상태 |
|---|---|---|---|
| REV-A01 · P1 | P0 계약 §3의 멱등 키가 주체·메서드·경로 범위와 저장 응답 재생 전 권한 검사를 정의하지 않음 | 내부 주체/메서드/정규화 경로/키를 묶고 인증·현재 자원 권한을 재생 전 검증. 동시 동일키는 한 실행. TTL·진행 중 응답·실패 보존은 구현 전 결정 필요 | DOCUMENTED, 구현 NOT_RUN |
| REV-A02 · P2 | §3이 If-Match와 멱등키를 대안으로 제시하여 다른 키의 동시 PATCH 갱신 유실 가능 | 수정·삭제·상태 변경의 버전 비교와 재시도 멱등성을 별도 책임으로 명시 | DOCUMENTED, 구현 NOT_RUN |
| REV-A03 · P2 | §5/§7에서 지원 승인만 잠금 정의, 정원 축소와 승인 경합 누락 | 정원·마감·종료 변경/철회도 같은 모집 행 잠금 규약. 정원은 모집자+승인 인원 이상 | DOCUMENTED, 구현 NOT_RUN |
| REV-A04 · P2 | §5 지원 경로에서 `{id}`를 부모/자식에 중복 사용 | `{recruitment_id}`/`{application_id}` 분리와 부모 FK 확인, 불일치 404 | DOCUMENTED, 구현 NOT_RUN |
| REV-A05 · P2 | NFR-SEC-001은 JWT만 허용, 새 계약은 인증 방식 미결정 | NFR ID를 유지하면서 FastAPI가 검증하는 세션/토큰 및 방식별 검증 요건으로 정합화. 공급자 선택 없음 | DOCUMENTED, 보안 승인 대기 |
| REV-A06 · P2 | FR-COM-004 CRUD에 비해 §5의 모집 삭제 경로/지원 이력 처리 누락 | DELETE·논리삭제를 **설계 후보**로 기록. 지원 이력, 보존/복구/고지 정책 승인 전 삭제 API 비활성. 종료를 삭제 완료로 표시하지 않음 | BLOCKED_POLICY |

위 항목은 학교의 실제 업무 규정이 아니라 신규 플랫폼의 설계 보완안이다. 새 역할 부여나 RLS SQL, 관리자 API, DB 마이그레이션, 서버 기능은 구현하지 않았다. 기존 92개 기능과 DEC-001~015의 ID 및 확정 방향은 보존한다.

## Claude Code의 추가 독립 리뷰

검토 대상은 동일한 PR #11 원 HEAD `219aff5377a6652db5f1797ac743c7880feeadd0`다. Claude CLI 버전은 `2.1.312`, 인증 상태는 `loggedIn=true`, `authMethod=claude.ai`, `apiProvider=firstParty`로 확인했다. 실행은 읽기 전용 plan 모드, `--tools ''`, hooks/MCP 비활성, 세션 지속 저장 비활성 조건이었다. 리뷰 결과의 모델 표기는 `claude-opus-5-5`이며 명령 결과는 success다. 도구 실행·파일 수정·서버 테스트를 허용한 리뷰가 아니므로 런타임 검증은 모두 NOT_RUN이다.

로컬 원문 아티팩트 이름은 `ditnow-claude-pr11-review.json`, SHA-256은 `D583E330ACC9DEAD6495E40EF66BE4417CD32BA043AC7D7F94774847BACE66D4`다. 원문 실행 메타데이터를 저장소에 통째로 복사하지 않고 검토 가능한 요약만 보존한다. 원문의 요약 건수와 개별 항목 번호가 일치하지 않으므로 건수로 합격을 판단하지 않고 아래 finding ID별 처리를 기록한다.

| Claude finding | 처리 | 근거와 남은 조건 |
|---|---|---|
| H1 감사·멱등·접근 로그의 익명 제2 원장 | 수용 | P0 계약/NFR-PRIV-003/DB·API 일반 감사 규칙에 익명 예외와 비식별화·접근 격리, rate-limit·분석·백업 검사 추가. 특정 HMAC·보존기간·테이블 이름은 선택하지 않음 |
| H2 / M7 / M8 | 기존 보완 수용 | REV-A01~03의 사용자 범위 멱등성·버전 필수·공통 모집 잠금으로 반영. 원문의 TTL/428 등 세부 값까지 자동 채택하지 않음 |
| H3 단일 앱 DB 자격 증명의 범위 | 추가 승인 게이트 | 일반 앱/관리자 승인/익명 신고/outbox의 권한 분리 후보를 검토하도록 명시. 전달받은 p_user를 비교하는 SECURITY DEFINER만으로 신원 위조가 해결된다고 보지 않음. DB/함수/연결 풀 배치는 OPEN-002/003 승인 필요 |
| H4 issuer/바인딩 | 수용 + 절차 보류 | 정확한 issuer/audience/alg·고정 키/JWKS 허용목록, 동적 jku/x5u 불신, 이메일 자동 연결/미등록 주체 자동 생성 금지 추가. 초대·바인딩 방식은 OPEN-002/003 승인 대기 |
| H5 정원 의미 / L5 RPC 표현 | 문서 정합화 수용 | FRD의 승인 수를 모집자 제외로 정의하고 변경 후 `1 + accepted_count ≤ capacity`로 맞춤. 기존 MVP도 `capacity - 1` 기준이므로 동작 의미 변경 없음. 필드명 변경 없음 |
| M1 인증 방식 | 기존 보완 + 게이트 | NFR-SEC-001의 JWT 고정을 제거. 로그아웃 후 거부 요구는 유지하며 실제 폐기/세션 방식은 OPEN-002에서 결정 |
| M6 대량 할당 | 수용 | 생성/수정 입력 허용목록·extra forbid·서버 소유 필드 입력 금지, 공고 연결 권한 재검사 추가 |
| M10 공유 캐시 | 일부 수용 | is_mine 사용자별 응답의 private/no-store·공유 캐시 금지와 공개 실시간 projection 추가. 공개 시각 절삭은 미승인 제안으로 보류 |
| M13 소속 권위 | 수용 | FRD/데이터 모델의 프로필 소속을 읽기 projection으로 명시하고 승인된 유효 active 멤버십 기준으로 정합화 |
| M2 / M3 / M4 / M5 / M11 / L6 | 후속 구현 검토 | CSRF·토큰 보관·CORS, RLS 미설정/풀 재사용 거부, NULL scope·기간 겹침, 관리자 부여 범위, 메시지 nonce 범위, cursor 검증은 관련 기능 구현 계약/테스트에서 검토. 구체 SQL·인증 방식·관리자 정책을 이 리뷰만으로 확정하지 않음 |
| M9 / M12 / L2 / L3 / L4 / L7 | 제안 보류 | 재지원 partial unique, users/identity_links 모델 변경, 필드/역할 모델·view 선택·예시 명령 수정은 별도 계약 리뷰 대상으로 유지. 재지원 허용이나 새 신원 모델은 승인 없이 도입하지 않음 |
| L1 공개 GET 200과 타인 PATCH 404 | 비채택 | 읽기와 변경 권한은 다르므로 상태코드 차이가 곧 설계 모순은 아님. 기존 소유권 실패 404 계약 유지 |

M8의 capacity 20 상한은 기존 FRD의 설계 기본값이며 승인된 영구 DB CHECK로 승격하지 않았다. Claude의 제안은 전체를 규범으로 복사하지 않았으며 위 수용·보류·비채택 결과도 사람의 정책 승인과 구분한다.

## 원 HEAD 시점의 정합성 확인과 제한

원 HEAD 검토 당시 FastAPI가 매 요청 인증·현재 역할/소속·자원 소유권을 검사하고 PostgreSQL 후보의 최소 GRANT/RLS가 추가 방어선이라는 문서 경계를 확인했다. 현재 기준은 위 MariaDB 사용자 결정과 갱신된 계약이다. 외부 `(issuer, subject)`와 내부 UUID, 익명 공개 응답과 비공개 작성자 원장, 실명 모집의 허용 프로필 응답 분리는 유지한다. 모두 문서 확인이며 보안 동작의 실행 검증이 아니다.

저장소 적격성은 [사용자 해결 확인 기록](02_HACKATHON_ELIGIBILITY.md)에 따라 개발 장애로 반복 분류하지 않는다. README의 관련 상태 문구는 병행 중인 백엔드 담당자의 변경 범위이며 이 PR에서 제외했다. 운영진의 해결 방식·승인 증빙을 새로 확인했다고 주장하지 않는다.

## 검증 증거

| 검사 | 실제 결과 | 한계 |
|---|---|---|
| `node scripts/check-agent-config.mjs` | PASS | 탐색/스킬 경로 검사이며 서버 검증 아님 |
| 변경 Markdown 상대 링크 검사 | PASS | 로컬 파일 존재 확인, 외부 URL 재조사 아님 |
| 기능 추적표 CSV 비교 | PASS, 92행/고유 92개·기존 ID 동일 | 변경된 기능 구현 없음 |
| DEC-001~015 행 비교 | PASS, 기존 행 동일 | 새 정책 승인 기록 없음 |
| API 경로 매개변수 중복 검사 | PASS | 라우트는 문서 계약이며 실제 서버 import 검사가 아님 |
| `git diff --check` | PASS | 공백/패치 정합성 |
| 과거 MVP 타입·빌드 | PR의 실제 GitHub Actions 결과로 확인 | 격리된 프로토타입 회귀 참고만 가능; 최종 시연/제출 구현 증거 아님 |
| 인증·권한·MariaDB·멱등 경합·삭제 | NOT_RUN | 접속정보·계정 권한·인증·정책 승인 선행 필요 |

후속 PR은 보안/NFR 계약에 영향을 주므로 자동 병합하지 않는다. PR HEAD와 일치하는 CI 결과는 GitHub PR에서 기록하고 사람 리뷰를 요청한다. 새 보고서의 탐색 안내는 병행 중인 NAV 담당자가 추가한다.

## 남은 승인과 다음 작업

DB 제품은 MariaDB로 확정되었다. OPEN-002의 남은 인증 방식/클라우드 접속정보·버전·운영 환경/비용, OPEN-003의 가상 권한 책임자·DB 계정 권한, OPEN-009의 보존·모집 삭제/지원 이력 처리, 익명 신고 담당자와 작성자 매핑 열람 절차가 남아 있다. 이 계약 보완은 사람 승인 전이며 실제 인증·DB 계정 생성이나 연결 허가로 사용하지 않는다. FastAPI 공통 기반과 신규 apps/web의 계약 기반 독립 작업은 진행할 수 있다.
