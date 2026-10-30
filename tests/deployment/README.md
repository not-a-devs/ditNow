# 서버 소유자용 공개 HTTPS 점검

- 태스크: `TASK-OWNER-HTTPS-SMOKE`
- 관련 요구사항: FR-AUTH-001/002, FR-AI-002, FR-OPP-004의 **공개 배포 경계 점검만** 지원한다. 해당 기능의 구현 완료나 인증·CRUD 검증을 대신하지 않는다.
- 관련 NFR: NFR-SEC-001/004, NFR-REL-004. 테스트 식별자는 `test_https_smoke.SmokeTests.test_*`이며 기능 요구사항 ID를 새로 만들지 않는다.
- 상태: 코드·오프라인 모의 검증 대상. 실제 서버 설치, 외부 공개, 실제 도메인 점검, 로그인·DB 검증은 **NOT_RUN**이다.
- 수정 범위: 이 디렉터리의 Python 파일 2개와 이 README. 배포 설정, DNS, Tunnel, DB, 비밀정보는 변경하지 않는다.

## 기본 실행: 접속하지 않음

Python 3.13 및 표준 라이브러리만 사용한다. 의존성 설치는 필요 없다.

```powershell
python tests/deployment/https_smoke.py
python -m unittest discover -s tests/deployment -p 'test_*.py' -v
```

기본 결과는 `NOT_RUN`, 요청 수 0이다. 테스트는 모의 HTTP 응답을 사용하고 소켓 연결을 막는다. URL이나 자격증명을 명령행 인수로 받지 않는다.

## 외부 공개를 별도로 승인받은 서버 소유자만 실행

아래 값은 승인 절차를 대신하지 않는다. 소유자는 실제 공개 승인, DNS·인증서·라우팅 준비를 먼저 확인한다. 이 태스크에서 실제 도메인에는 접속하지 않는다.

```powershell
$env:DITNOW_HTTPS_SMOKE_RUN = '1'
$env:DITNOW_HTTPS_SMOKE_APPROVED = '1'
python tests/deployment/https_smoke.py
Remove-Item Env:DITNOW_HTTPS_SMOKE_RUN
Remove-Item Env:DITNOW_HTTPS_SMOKE_APPROVED
```

대상은 코드에 고정된 `https://dit.sunghae.xyz` 하나다. 환경 변수로 변경하지 못한다. 인증서와 호스트 이름을 시스템 기본 신뢰 저장소로 검증한다. 검증 해제 옵션·프록시·리디렉션 추적·재시도·로그인·쿠키·Authorization 헤더가 없다. 요청당 타임아웃 5초, 본문당 2 MiB, 전체 본문 8 MiB, 자산 최대 12개이며 고정 경로 5개를 더해 요청은 최대 17회다. 실패 시 자동 반복하지 않는다.

## 확인 범위와 결과

| 검사 | 성공 조건 |
|---|---|
| `/app`, `/app/ai` | 직접 접근 200, HTML, React root·module 진입점, 동일 배포 진입점 |
| `/api/v1/health` | 200 JSON, `data.status=ok`, `data.service=ditnow-api` |
| `/api/v1/auth/me`, `/api/v1/me/saved-opportunities` | 비로그인 401 JSON `UNAUTHORIZED`, `Cache-Control: no-store` |
| 정적 자산 | 발견한 모듈·CSS·선언 자산의 같은 HTTPS origin, 200, JS/CSS 형식, 제한 내 후속 import/CSS URL |
| 하드코딩 URL | 발견한 URL 리터럴의 HTTP·localhost·사설 IP·외부 `/api/` 주소 거부 |

인증이 미설정되어 404/503이면 `AUTH_NOT_READY` 실패다. 200 로그인 우회나 HTML로 대체된 JS 파일도 실패다. 3xx는 목적지로 요청하지 않고 실패한다. 일반 안전 검사 코드의 `localhost` **문자열만**으로 실패하지 않는다. React/SVG의 고정 표준 namespace 식별자는 네트워크 URL이 아니므로 허용한다. 외부 HTTPS 문서 링크는 자산 요청과 구별하며, 실제 자산은 모두 같은 origin이어야 한다.

- `NOT_RUN`: 승인 opt-in 부족, 요청 0, 종료 코드 0. 추가 인수는 종료 코드 2.
- `FAIL`: 하나라도 실패, 종료 코드 1. 응답 본문·원문 예외·임의 URL은 보고서에 출력하지 않는다.
- `PUBLIC_SMOKE_PASS`: 위 공개 경로만 통과, 종료 코드 0. **서비스 전체 PASS가 아니다.** `verified_claim=false`, `authenticated_crud=NOT_RUN`, `deployment_approval=NOT_VERIFIED`를 유지한다.

이 도구는 브라우저를 실행하지 않는다. 정적 URL 리터럴/선언 참조만 검사하므로 런타임 계산 URL, 지연 로딩 전체, WebSocket, CSP, 모든 요청·접근성·레이아웃·서버 데이터 무결성을 입증하지 않는다. 외부 HTTPS 문서·이미지의 안전성이나 전체 애플리케이션 보안을 보장하지 않는다. 자산 수 제한에 걸리면 검사를 생략해 성공하지 않고 실패한다.

## 후속 승인·직접 검수

실제 배포·비밀 주입·DB 연결과 테스트 계정 사용은 별도 승인 후 서버 소유자가 수행한다. 다음은 이 도구에서 실행하지 않는다.

1. 신규 앱에서 가상 계정 A/B 로그인, 메모리 세션·로그아웃·재로그인·새로고침 확인.
2. 익명 게시글, 실명 모집, 개인 기회 준비의 실제 API→MariaDB CRUD와 서버 재조회 확인.
3. B의 A 자원 접근 거부, 익명 응답의 작성자 신원 비노출, 토큰 폐기 확인.
4. 390/1280 브라우저 검수, 실패·부분 성공·재시도와 테스트 marker에 한정한 정리 확인.
5. 테스트 세션 폐기와 남은 테스트 레코드·기존 원장 보존을 서버 소유자가 확인.

기존 `tests/e2e/`의 승인·요청 quota·비밀 출력 방지·자기 marker 정리 규칙을 따른다. 본 도구의 공개 경로 통과를 실제 로그인, DB 영속성, 두 계정 격리나 배포 승인으로 보고하지 않는다.

## 작성 시 검증 기록

2026-10-30, Python 3.13에서 오프라인 unittest **20개 PASS**, Ruff 정적 검사·포맷 검사·Git diff 검사 PASS. 기본 실행 결과 `NOT_RUN`, `requests=0`을 확인했다. 인증서 검증 설정은 모의 연결 객체로 검사했으며 실제 인증서·DNS·서버에 접속한 증거가 아니다. 실제 공개 도메인 검사와 로그인·DB 검증은 NOT_RUN이다. GitHub CI 결과와 독립 리뷰는 PR의 정확한 HEAD를 기준으로 별도 기록한다. 신규 경로를 NAV와 CI에 등록하는 변경은 공통 파일 소유자의 후속 통합 범위다.
