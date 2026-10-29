# TASK-P0-LIVE-FE — 신규 앱 로그인과 핵심 CRUD 연결

2026-10-30 KST. **IMPLEMENTED / TESTED(프런트 테스트 범위)**. 실제 DB·배포·브라우저 통합은 이 작업자가 실행하지 않았으며, 전체 기능을 VERIFIED로 표시하지 않는다. 사전 프로토타입 `mvp/`를 읽거나 복사하지 않고 신규 `apps/web/`를 연결했다.

## 기준과 소유

- 승인된 통합 기준: `integrate/p0-live-foundation-20261030`의 `7f7eabbb44f09caeaac79798baab8a69485ab453`. 당시 main 미병합인 공통 인증·MariaDB·프로브·로그인 UI 제안들을 포함하므로 이 프런트 PR 단독으로 운영 활성화를 승인하지 않는다.
- 소유: 신규 App·메뉴·아이콘, `features/auth/MemoryAuth.tsx`, 공통 HTTP 전송·요청 수명 hook, 기존 community/opportunities 연결 보강, 전용 테스트 및 이 문서.
- FastAPI·Settings·DB·migration·시드·공통 OpenAPI/생성 타입·NAV는 각각 기존 담당자가 소유한다. 이 작업에서 변경하지 않는다. 실제 서버·DB 검증과 시연 계정 생성은 통합 담당자의 별도 승인·검증 범위다.
- 연결 요구사항: FR-AUTH-001/002(현재 신원 검증 부분), FR-COM-001/004, FR-OPP-001(공개 조회)/003/004. 전체 92개 범위를 축소하지 않는다.
- 연결 기준: DEC-015/017/018/020, NFR-SEC-001/002/004/005/007, NFR-PRIV-002/003, NFR-REL-001, NFR-UX-001/003; TC-V1-AUTH-001, TC-V1-COM-001/004, TC-V1-OPP-001/003/004, TC-V1-X03의 해당 부분.

## 동작과 보안 경계

1. `/app/login`은 기존 학번·비밀번호 로그인 API만 호출한다. 응답의 정확한 DEMO 계약을 검사한 뒤 단일 메모리 소유자가 토큰을 보관한다. 클라이언트 계정·역할·UUID·만료 시각을 생성하지 않는다.
2. 새 `GET /api/v1/auth/me`의 `user_id/display_name/record_source/department_id/department_code/academic_year/community_access`를 검사해야 보호 모듈을 연다. `/auth/me` 대기 중에는 다른 보호 요청을 보내지 않는다. 503·손상 응답은 로그인 성공이 아니다.
3. 서버가 각 요청의 현재 권한·소유권을 결정한다. `community_access`는 화면 안내만 제어하며 인가 근거가 아니다. 토큰·비밀번호는 저장소·URL·로그에 남기지 않으며 새로고침하면 로그인이 해제된다.
4. `requestData` 한곳에서 보호 경로에만 Authorization을 주입한다. 공개 조회는 호출자가 제공한 Authorization도 제거한다. 보호 전송은 no-store/omit credentials/no redirect/no referrer, HTTPS 또는 loopback HTTP만 허용한다.
   독립 검토에서 발견된 raw 경로와 URL 정규화 차이를 막기 위해 literal `.`/`..` segment도 접속 전에 거부한다. 학년에는 학교 정책처럼 임의 상한20을 두지 않고 안전하게 표현 가능한 양의 정수만 검사한다.
5. 로그아웃은 먼저 메모리와 개인 화면·초안을 폐기하고 진행 중 요청을 취소한다. 폐기는 캡처한 이전 토큰으로만 요청한다. 서버 폐기 실패는 로컬 로그아웃과 구분하며 이전 계정의 늦은 결과가 새 계정을 변경하지 못한다.
6. 보호 응답 401/403은 현재 세션의 개인 하위 화면 전체를 제거한다. 요청 세대·AbortSignal·layout cleanup과 동기 busy guard로 StrictMode·동시 제출·unmount·계정 전환 뒤 응답·재조회를 차단한다. Abort는 이미 서버가 처리한 쓰기를 되돌린다는 보장이 아니다.

## 연결된 화면

- 익명 커뮤니티: 서버 목록, 멱등 생성, revision 기반 수정·삭제, 매 변경 후 서버 재조회. 익명과 실명 모집은 분리한다.
- 팀원 모집: 생성·수정·마감과 별개로 승인된 `DELETE /recruitments/{id}?revision=N`을 open 본인 글에 연결한다. 이는 기존 `cancelled` 논리 취소이며 물리 삭제·이력 제거가 아니다. closed→cancel은 기존 409를 유지한다. 타인 수정·삭제 제어의 최종 근거는 서버다.
- 기회: 공개 공고 조회·상세와 개인 저장·준비 상태·체크리스트 CRUD. 공개 공고에는 토큰을 붙이지 않고 개인 준비 경로에만 붙인다. 외부 기관에 실제 제출하지 않는다.
- 재조회 실패·409·503은 가짜 목록으로 대체하지 않는다. 목록 API의 첫 페이지를 보여주며 전체 데이터의 완전한 열거·검색을 주장하지 않는다. 나머지 92개 기능은 이번 작업에서 완료하지 않는다.

## 검증

| 검사 | 실제 결과 |
| --- | --- |
| `npm ci` | PASS, 잠금 설치 |
| `npx vitest run src/lib/auth-transport.test.ts src/features/auth src/features/community src/features/opportunities src/App.test.tsx` | PASS, 8파일84개(새 App 통합 테스트 추가 전 체크포인트) |
| `npx vitest run src/App.auth.test.tsx` | PASS, 최종9개. 이전 계정의 늦은 logout 403이 새 계정을 해제하지 않는 회귀 포함 |
| `npx vitest run src/lib/auth-transport.test.ts src/App.auth.test.tsx` | 독립 검토 보완 후 PASS, 2파일22개(공통 전송13 + App9). literal dot path3·학년 계약1 회귀 추가 |
| `npm run test` | PASS, 32파일410개(후속 logout 회귀 추가 전 체크포인트) |
| `npm run typecheck`, `npm run build` | PASS |
| `npm audit --audit-level=moderate` | PASS, 취약점0 |
| `node scripts/check-agent-config.mjs`, `node scripts/check-feature-progress.mjs` | PASS, NAV90·8 mirrored skills·92개 추적(당시 통합 base) |
| `git diff --check` | PASS |
| 실제 HTTP→FastAPI→MariaDB·운영 브라우저/재시작 영속성 | NOT_RUN by this author. 통합 담당자 검증 게이트 |

테스트의 fetch double은 테스트 파일에만 있다. 런타임 fake 계정·공고·DB·로컬 저장 fallback을 추가하지 않았다. 새 서버 HEAD의 OpenAPI 생성 및 CI는 공통 담당자가 조정한 뒤 같은 최종 HEAD에서 확인해야 한다. 보안·인증 변경 PR의 승인과 실제 원장 활성화를 이 문서의 로컬 테스트로 대체하지 않는다.
