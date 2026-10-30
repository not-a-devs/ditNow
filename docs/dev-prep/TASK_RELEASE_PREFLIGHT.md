# TASK-RELEASE-PREFLIGHT — 기존 인프라용 오프라인 설정 진단

기준: main `49cf5759c9f0694dbf6e59455f138895d697c28f`, 2026-10-30.

## 범위·상태

사용자 확인으로 심사용 도메인·배포 인프라는 이미 준비되어 있다. 새 호스팅 선정·컨테이너·클라우드·비용 발생 없이 기존 인프라를 사용한다. **서버 상세 정보 미수신만 BLOCKED**이며, 실제 외부 배포·공개 서비스 기동에는 별도 승인이 필요하다. 주소·서비스 관리자·프록시·실제 환경 값을 추정하지 않는다.

- 관련 요구사항: NFR-SEC-004/005, NFR-OPS-001/002, NFR-REL-001/003. 기존 92개 FR·인증·DB·사용자 결정은 유지한다.
- 상태: CLI와 합성 설정 검사는 **TESTED**. 실제 운영 환경·비밀 저장소·DB·CA 내용·서비스 기동·LLM·배포는 **NOT_RUN**.
- 생성 파일은 CLI·전용 테스트·이 문서 3개다. 기존 Settings·런타임·DB factory·lockfile·README·NAV는 수정하지 않는다.

## 기존 도구 재사용과 추가 이유

[기존 DB 진단](../../services/api/app/core/db_connection.py)의 `configuration_report()`와 [Settings](../../services/api/app/core/config.py)를 재사용한다. 기존 `python -m app.core.db_connection`도 네트워크 없는 진단이지만 DB 미설정에서 exit 0이며 P0 활성 조건이나 운영 의도를 판정하지 않는다. 그 결과만으로 로그인 가능한 배포 설정이라고 판단하면 안 된다.

[새 CLI](../../services/api/app/operations/release_preflight.py)는 이 검증 위에 `public` 또는 `p0` 목적을 명시해 누락·충돌만 찾는다. 앱·SDK·DB 엔진·CA loader·migration·시드를 만들거나 외부에 접속하지 않는다. Settings는 기존과 같이 dotenv를 읽지 않는다. `db_tls_ca_file`이 설정되었다면 기존 FilePath 검증이 경로의 존재를 검사할 수 있지만 CLI가 CA 내용을 열거나 지문을 검증하는 것은 아니다.

## 실행과 출력

운영자가 승인된 외부 주입 방식으로 환경을 제공한 뒤 `services/api/`에서 실행한다. 비밀번호·토큰·주소·CA 경로·감사 UUID를 명령 인자에 넣지 않는다. 이 작업자는 실제 환경에 대해 실행하지 않았다.

```text
uv run --locked python -m app.operations.release_preflight --profile public
uv run --locked python -m app.operations.release_preflight --profile p0
```

두 명령은 서로 다른 진단 목적이며 자동으로 연속 실행하는 배포 스크립트가 아니다.

| 항목 | 의미 |
| --- | --- |
| `configuration=PASS`, exit 0 | 선택한 목적의 로컬 설정 진단만 통과 |
| `configuration=FAIL`, exit 2 | 정적 `codes`를 보고 설정 누락·충돌을 검토 |
| `SETTINGS_INVALID` | 기존 Settings 검증 실패. 입력 값·예외 원문은 출력하지 않음 |
| `INVALID_ARGUMENTS` | 목적 누락·잘못된 인자. argv 원문·오타에 포함된 비밀도 출력하지 않음 |
| 나머지 `NOT_RUN/NOT_VERIFIED` | 실제 배포·DB·권한·TLS pin·인증 승인·프록시·LLM을 확인하지 않았다는 고정 상태 |

PASS는 DEPLOYED·READY·학교 정책 승인·감사 행의 유효성·비용 승인이 아니다. 실제 서버 설정을 바꾸거나 앱의 허용 설정을 제한하지 않는 **보수적인 오프라인 진단 기준**이다.

## 진단 기준

- 공통: production 환경, 기본 비공개 문서 정책 검토, 명시 CORS의 HTTPS 검토, legacy `DATABASE_URL` 충돌, 양의 요청 제한을 검사한다. `DOCS_EXPOSURE_REVIEW_REQUIRED`와 `HTTPS_CORS_REVIEW_REQUIRED`는 운영 문서 공개·HTTP origin을 보수적으로 재검토하라는 코드이며 새 학교 정책을 확정하지 않는다.
- `public`: 공개 검색만을 대상으로 하므로 DB가 없어도 된다. P0가 활성화되어 있으면 목적 불일치로 실패한다. 빈 CORS는 동일 origin 프록시 후보와 양립하지만 실제 프록시의 존재나 안전성을 증명하지 않는다.
- `p0`: runtime 활성, 완전한 기존 DB 설정, schema 사전 검토 flag, 비어 있지 않고 중복 없는 감사 UUID 목록이 필요하다. DB가 없거나 gate 일부만 있으면 실패한다. 임의 UUID의 존재·승인 효력·현재 역할은 조회하지 않으며 실제 인증 승인 원장 검증은 NOT_VERIFIED다.
- LLM: provider 없는 모델·키·base 설정, provider에 필요한 모델·키·호환 base 누락, 활성 provider의 유효하지 않은 timeout을 검사한다. 기존 호환 클라이언트는 승인된 무키 서버를 지원하므로 키를 임의로 필수화하지 않는다. 설정 통과를 모델 선택·비용·개인정보 전송 승인이나 실제 생성 성공으로 취급하지 않는다.
- 출력에는 설정 값·host·DB 사용자·감사 UUID·CA 경로·모델·API 키·DSN·오류 원문을 넣지 않는다. 인자 파싱 실패도 고정 코드만 출력한다.

## 남는 실제 배포 게이트

[기존 배포 준비 문서](TASK_DEPLOYMENT_PREPARATION.md)의 검토 절차를 유지한다. 그 문서는 이전 실행 SHA의 기록이므로 실제 P0 성공·이후 병합 상태는 최신 검증 문서와 구분한다.

1. 수신할 서버의 OS·프로세스 관리자·서비스 실행 계정·release 경로·역방향 프록시 정보를 대조한다. API만 복사하면 `../../chatbot`의 잠금 로컬 의존성이 깨질 수 있으므로 두 경로의 배치를 유지한다. Python 3.13·고정 uv·웹의 Node 22 환경과 같은 release SHA의 빌드를 사용한다.
2. 기존 도메인의 HTTPS·SPA 직접 진입·API prefix와 JSON 404·Authorization/If-Match/Idempotency-Key·no-store 보존, 현재 CORS의 정확한 origin/method/header를 실제 ingress에서 검사한다. CLI는 웹 번들의 API 주소나 프록시를 읽지 않는다.
3. Windows는 `app.core.event_loop:new_event_loop`의 Selector 호환 경로, Linux는 기본 asyncio 경로를 기존 실행 지침과 대조한다. 초기 단일 worker·replica 및 proxy trust는 운영 명령에서 별도로 확인한다. Settings만으로 process/host trust를 검증할 수 없다.
4. 기존 Tailscale MariaDB 경로·ACL·CA/SAN/pin·현재 GRANT·schema checksum·승인 identity binding을 운영자가 별도 확인한다. `configuration_report()`의 과거 고정 schema 상태를 실제 최신 DB 판정으로 재사용하지 않는다. migrator 자격·자동 DDL·새 DB 컨테이너는 앱 실행 환경에 넣지 않는다.
5. health 200은 업무 readiness가 아니다. 승인된 동일 release에서 실제 localhost·외부 HTTPS·두 계정 거부·지속성·로그아웃·정리와 롤백 절차를 각각 검증한다. 공개 URL·운영 배포·LLM 호출을 이 CLI나 CI 성공으로 승인하지 않는다.

## 검증

- [전용 합성 테스트](../../services/api/tests/test_release_preflight.py): 현재 작업자 환경의 DIT 설정을 격리한 후 값이 없는 보고, 각 gate·목적 충돌·오류·중복 pin·LLM 누락·네트워크/실제 dotenv·secret-file 읽기 금지·인자 비밀 누출을 검사한다. 실제 자격 정보는 쓰지 않는다.
- 기존 DB 설정/TLS/Windows 루프 검사도 재사용한다. 실제 서버·DB·TLS 연결 검사로 해석하지 않는다.
- 실제 검사: 신규32개 + 기존 DB24개 + 루프7개 = **63 PASS**. 전체 API **1,513 PASS**(기존 Starlette TestClient 사용 중단 예정 경고 1개), 전체 Ruff·포맷237개·OpenAPI 일치 PASS.
- 에이전트 설정105경로/스킬8쌍·92개 기능 추적·문서 상대 링크5개·Git diff 검사 PASS. 새 PR HEAD CI는 별도로 확인하고 PR에 기록한다.
- 운영 환경을 읽거나 서비스를 시작하지 않았으며 실제 배포와 LLM 생성은 NOT_RUN이다. NAV와 README는 공통 문서 소유자가 통합한다.
