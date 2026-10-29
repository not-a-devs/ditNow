# TASK-FE-AUTH — 신규 플랫폼 로그인 화면

상태: **IMPLEMENTED / TESTED(프런트 단위 범위)**, 전역 App 미마운트, 기본 비활성. FR-AUTH-001의 신규 프런트 범위만 다루며 전체 요구사항은 PARTIAL이다. FR-AUTH-002 역할/소속 승인과 FR-AUTH-003 프로필 업무는 완료하지 않는다. DEC-017/018/020, RBAC-AUTH, NFR-SEC-001/002/004/005/007, NFR-PRIV-003, NFR-UX-001/003, TC-V1-AUTH-001에 연결한다.

## 파일 소유와 경계

- 소유: `apps/web/src/features/auth/`의 API 전송·응답 검사·React 폼·CSS·테스트와 이 문서.
- 공유 `App`, navigation, `lib/api`, OpenAPI, backend, 인증/DB 원장·migration·NAV는 변경하지 않는다. 통합 담당자가 승인 이후 별도 연결한다.
- 새 React 코드를 작성했으며 `mvp/` 소스를 읽거나 복사하지 않았다. 가상 계정 자격을 코드·기본 입력·도움말에 하드코딩하지 않는다.

## 실제 API와 상태 계약

현재 main DEC-020의 `POST /api/v1/auth/login`에 `{student_id,password}`만 전송한다. 학번 1~20자, 비밀번호 1~64 Unicode code point이며 비밀번호 공백을 정규화하지 않는다. 성공 DTO의 `token`, `Bearer`, `student_id`, `name`, `record_source=DEMO`를 allowlist로 검사하고 요청한 학번과 다르면 거부한다. 상한 없는 서버 token/name에 프런트 자원 보호용 4096 ASCII 토큰·200문자 이름 상한을 두며 이는 계정·권한 정책이 아니다. 이 범위를 넘는 승인된 표시값이 필요하면 공통 계약 소유자와 조정한다.

`POST /api/v1/auth/logout`은 Bearer를 Authorization 헤더로만 전송한다. 정확한 `{status:ok}` 응답만 서버 로그아웃 확인으로 표시한다. 실패해도 `onSignedOut(local_only)`로 로컬 세션 제거를 요청하고 서버 폐기 미확인을 명시한다. 401은 `expired`로 분리한다. 자동 네트워크 재시도는 없다.

컴포넌트는 기본 `enabled=false`이며 요청하지 않는다. 활성화되더라도 세션을 소유하지 않는다. 상위 공통 인증 소유자가 메모리 상태를 하나만 관리한다:

```tsx
<PlatformLogin
  enabled={false} // 승인 후 통합 소유자만 변경
  session={{ state: 'signed_out' }} // 또는 expired / signed_in + 검증된 session
  onSignedIn={acceptIntoSingleMemorySession}
  onSignedOut={clearSingleMemorySession}
/>
```

위 이름은 연결 계약 예시이며 이 PR에 실제 provider·통합 App·전역 인증이 구현되었다는 뜻이 아니다. `onSignedIn`으로 토큰을 한 번 전달하고 자체 영속 저장하지 않는다. 소유자는 callback 예외를 기록할 때 토큰/비밀번호/응답 원문을 출력하지 않아야 한다. 상위 `signed_in`은 UI 상태이며 실제 권한 근거가 아니다. 현재 LoginData에는 UUID·역할·소속·expires_at이 없으므로 임의 identity를 만들거나 클라이언트 TTL로 권한을 결정하지 않는다. 보호 API의 401과 공통 소유자의 상태로 만료를 전달한다.

## 안전·UX

- 비밀번호는 제출 직후 입력란에서 지우고 요청 closure에만 둔다. 토큰/비밀번호의 localStorage·sessionStorage·URL·콘솔 저장/출력은 없다.
- HTTPS 또는 로컬 loopback HTTP만 자격 정보를 전송한다. 쿠키 전송·캐시·redirect·referrer를 사용하지 않는다. API 오류 원문·이름을 비밀 로그로 출력하지 않는다.
- 동기 busy ref로 중복 제출을 막고 AbortSignal·요청 세대로 unmount/비활성화/세션 변경 뒤 결과를 폐기한다. StrictMode의 중복 effect로 자동 로그인이 발생하지 않는다.
- 가상 데이터 표시, 명시적 label, 오류 alert·상태 안내, keyboard focus, 390px 레이아웃을 제공한다. 503은 서버 미준비이며 성공 콜백을 호출하지 않는다.
- 화면 제거·네트워크 손실 직전 서버가 토큰을 발급했는지는 이 컴포넌트가 확인할 수 없다. 임의 재로그인/다른 토큰 폐기를 수행하지 않으며 서버 만료·폐기 정책은 공통 인증 소유자의 승인 게이트다.

## 검증·차단

전용 테스트는 입력/실제 전송 계약·DEMO 출처/범위 검사·안전 오류·로그/저장소 미사용·중복 제출·콜백·StrictMode·취소/늦은 응답·만료·로그아웃 성공/미확인을 다룬다. 로그아웃의 상위 콜백 오류를 네트워크 오류로 오해하여 두 번 호출하지 않는 회귀도 포함한다.

| 검사 | 실제 결과(2026-10-30, base main `18a7846`) |
| --- | --- |
| 잠금 설치 `npm ci` | PASS, 취약점0 |
| 전용 `vitest run src/features/auth/api.test.ts src/features/auth/index.test.tsx` | PASS, 2파일22개. 독립 Codex 검토자도 직접22개 PASS |
| `npm run typecheck`, `npm run build`, `npm run api:types:check` | PASS. 미마운트 기능이 전역 앱에 활성화되었다는 의미는 아님 |
| `npm test` 전체 기본 병렬 실행 | **FAIL: 318/322 PASS**, 기존 `classrooms/index.test.tsx`의 과제409/401/403 안내·unmount signal 4개 실패. 이 결과를 전체 성공으로 표시하지 않음 |
| 기존 강의실만 `vitest run src/features/classrooms/index.test.tsx` | PASS, 9개 |
| 신규 인증2파일+강의실1파일 `vitest run ... --maxWorkers=1` | PASS, 31개. 전체 병렬 실패 원인은 확정하지 못했고 공유 테스트/설정을 수정하지 않음 |
| `npm audit --audit-level=moderate` | PASS, 취약점0 |
| 에이전트·추적표·diff 검사 | PASS, NAV84경로/8개 스킬/92개 FR. 신규 탐색 등록은 공유 소유자 후속 |

독립 읽기 전용 검토는 기존 실제 auth 스키마와의 일치, 토큰 전달·비영속화·HTTPS·abort/세대 폐기와 로그아웃 경계를 확인했고 현재 비활성 범위의 차단 finding이 없었다. 이는 사람 승인이나 실서비스 보안 검증이 아니다. 새 PR HEAD의 GitHub CI는 PR 본문에 별도 기록하며 이전 커밋의 성공으로 대체하지 않는다.

실제 서버/DB 로그인·계정 발급·공통 UUID bridge·보호 기능 권한·세션 원장·전역 App/챗봇 로그인 연결·다중 계정/재시작·브라우저 E2E는 NOT_RUN/별도 승인 대상이다. 운영 API·DB·비밀정보·네트워크를 이 태스크에서 변경하거나 접근하지 않는다. 인증 UI PR이므로 CI/AI 리뷰 성공도 사람의 운영 활성화 승인으로 간주하지 않으며 자동 병합하지 않는다.
