# TASK-PR-BATCH-MERGE — 승인된 PR 순차 병합

확인일: 2026-10-30 KST. 사용자 지시: **“다 머지해”**. 해당 시점의 인증·권한·DB PR을 포함한 코드 병합 승인으로 기록하며, 배포·과금·실제 계정 생성·운영 활성화 승인과 구분한다. 원래 작업 트리의 미커밋 조사 문서와 다른 작업자의 브랜치·worktree는 보존했다.

관련 요구사항: 기존 92개 FR 및 NFR-SEC/PRIV/REL/OPS, 테스트는 각 PR 작업 문서의 기존 TC를 유지한다. 기능·권한 정책을 임의로 추가하지 않았다.

## 실행 기준

- 최신 원격 PR HEAD와 실제 GitHub CI를 확인하고 독립 검토의 차단 지적을 수정한 뒤 Merge commit 방식으로 병합했다.
- 예상 HEAD 일치 옵션을 사용했고 강제 Push·관리자 우회·필수 검사 생략을 하지 않았다.
- 커밋·PR·병합 메시지는 한국어로 작성했다.
- PR #28의 최신 main 병합 충돌은 설정 import 한 곳이었다. DB 설정과 챗봇 안전화 검증을 모두 보존했다. 새 HEAD `62c116a84cbd5de2b9c926f3d0d37a58d2e16a41`의 실제 CI 5종 성공 및 root 전체 API 1113개 성공 후 병합했다.

## 병합 이력

| PR | 범위 | 확인한 병합 SHA |
|---|---|---|
| [#13](https://github.com/not-a-devs/ditNow/pull/13) | MariaDB·공통 원장 계약 | `515dacb872b9571b477f08567854502f593fab18` |
| [#54](https://github.com/not-a-devs/ditNow/pull/54) | 저장소·명시적 마이그레이션 | `f2fca47ec08e6429e2b2fffe5f8dd802ef932c68` |
| [#19](https://github.com/not-a-devs/ditNow/pull/19) | 공통 모델, #54의 선행 커밋으로 포함 | `09ae1e723b1e26b39c3ba6ef21a2af2915d42a51` |
| [#26](https://github.com/not-a-devs/ditNow/pull/26) | TLS 설정, #54의 선행 커밋으로 포함 | `ed2088a2c0e736a27f7a733514b3f2882efbd9b8` |
| [#37](https://github.com/not-a-devs/ditNow/pull/37) | SQL 저장소, #54의 선행 커밋으로 포함 | `27ff51759f7d105b054fc4c993370dd7ed790687` |
| [#58](https://github.com/not-a-devs/ditNow/pull/58) | 롤백 전용 DB CRUD 검증 도구 | `129d0ace8bfb7db6d9e3fde4f98454e5cdd25113` |
| [#49](https://github.com/not-a-devs/ditNow/pull/49) | 학번 세션·UUID 연결 계약 | `e428773e499dec892c1945c4c22964191bb15967` |
| [#48](https://github.com/not-a-devs/ditNow/pull/48) | 신규 로그인 화면 계약 | `3be8bada4e493e373e0ee57caa31ab0414c3b5b3` |
| [#52](https://github.com/not-a-devs/ditNow/pull/52) | 채널·소속 변경 노출 회귀 수정 | `76cd90db62e7b4735a79a3eaef58abada93c5535` |
| [#56](https://github.com/not-a-devs/ditNow/pull/56) | 학적 변경과 분리된 프로필 | `cfd9652700411d40b9449f0d2e156494cbd71237` |
| [#57](https://github.com/not-a-devs/ditNow/pull/57) | 가상 캠퍼스 이동 시간 계산 | `11dec9d105c85fb91d8c63eb223ddf3c1a839f0b` |
| [#53](https://github.com/not-a-devs/ditNow/pull/53) | 현재 권한을 적용한 기회 매칭 | `1273bc354055b5a3539f680f05832944ab549697` |
| [#47](https://github.com/not-a-devs/ditNow/pull/47) | 화면 공유의 미활성 기반 | `c1877f9136fb8d3cf633882acb5988afc6c32a67` |
| [#28](https://github.com/not-a-devs/ditNow/pull/28) | 챗봇 자동 초기화·비밀 로그 차단 | `60b9ca0f15778ae62db72efdb1be33329be0abc7` |
| [#61](https://github.com/not-a-devs/ditNow/pull/61) | 공통 로그인·핵심 CRUD 통합 API | `1dec0917a921e719505e19808d30585817775587` |
| [#60](https://github.com/not-a-devs/ditNow/pull/60) | 신규 앱 메모리 세션·API 연결 | `6c339edcb162d5ed6e9855593995e2036bd0f901` |
| [#59](https://github.com/not-a-devs/ditNow/pull/59) | 명시적 가상 계정 생성 도구 | `479be137171f5716be7c89faaaa79adc71a233f8` |
| [#63](https://github.com/not-a-devs/ditNow/pull/63) | 두 계정 HTTP 보안 검사 도구 | `46fcc7bee375b4fdd76b9c924fa1a36195dd83e4` |
| [#65](https://github.com/not-a-devs/ditNow/pull/65) | 알림 읽음/요약 재조회 검증 경합 수정 | `c18f49d14103d69c8f95613eb6a7088703ab32b1` |

## 독립 검토와 실제 검사

- #52: 작성자와 별도 Codex가 소속 철회 최소 응답과 이전 학과 응답 차단을 재검토했다. 독립 백엔드 100개·프런트엔드 36개 성공.
- #53: Claude 독립 리뷰의 여섯 지적 보완 후 root가 diff를 읽고 백엔드 112개·프런트엔드 31개를 직접 통과했다.
- #57: root가 서비스/UI 원문을 검토하고 백엔드 25개·프런트엔드 20개를 직접 통과했다.
- #61: 별도 Codex가 현재 권한·동일 업무 트랜잭션·토큰·익명 DTO·논리 취소를 읽기 검토하고 전용 HTTP/SQLite 29개를 직접 통과했다. 최신 main 조합의 PR CI 5종도 성공했다.
- #60: 별도 Codex가 세션 교체·이전 응답·자격 헤더 경로·논리 취소를 검토했다. 경로 정규화와 임의 학년 상한을 보완했고 새 HEAD `5cc4983f8e81899215715078237acdf93d973770`의 CI 5종 성공을 확인했다. 해당 CI의 웹 531개·API 1338개 성공은 모의/격리 DB 테스트이며 원격 E2E가 아니다.
- #59: 별도 Codex의 리뷰 지적 후 commit 성공·불명 상태를 연결 정리 오류 뒤에도 보존하도록 수정했다. root가 보완 diff를 검토하고 전용 36개를 직접 통과했다. 최종 HEAD `a4ae77b22881383a2c490ced1171acf1e4c2353a`의 CI 5종 성공 후 병합했다.
- #63: 별도 Codex가 보안 검사 도구와 모의 HTTP 24개를 직접 검증했다. 최종 HEAD `38ef9cbe39dfef7659cb6f1b2f7e73e56184315a`의 CI 5종 성공 후 병합했다.

AI 검토는 별도 세션에서 수행했지만 사람의 공식 검토를 대신하지 않는다. 사람의 병합 승인은 위 사용자 지시이며 검토·CI 결과와 별개로 기록했다.

### 문서 PR 검사에서 발견한 비동기 테스트 경합

PR #64 최초 웹 CI `40934970874`는 알림 읽음 테스트에서 후속 summary 호출이 시작되기 전에 즉시 호출 수를 검사해 실패했다. 실패를 단순 재실행으로 덮지 않았다. PR #65는 읽음 POST와 요약 응답을 각각 deferred로 제어해, 성공 전 읽음 표시·추가 조회가 없고 성공 뒤 정확히 한 번 재조회하며 그 응답의 미읽음 0을 표시하는지 검증한다. 기대값을 낮추거나 업무 코드를 바꾸지 않았다.

root가 기존 업무 코드와 변경 diff를 독립 검토했고 전용 9개·전체 웹 531개 성공 및 최종 HEAD `d0dd1f7ec4bcd80bda5e5661970002be0efdb8ff`의 CI 5종 성공 후 병합했다. 문서 브랜치에도 최신 main을 병합해 새 HEAD 검사를 수행한다. 기존 실패 CI를 성공했다고 재표기하지 않는다.

## DB와 서비스 검증 경계

이전 root 실행에서 엄격한 CA·호스트 검증을 유지한 MariaDB TLSv1.3 접속을 확인했다. 명시적 migrator 실행으로 `p0-initial-v1` 신규 테이블 16개를 적용했고 기존 9개 테이블의 정의·행 수를 보존했다. 총 25개 테이블의 InnoDB·문자셋·트리거 0 메타데이터를 확인했다. 비밀값·원본 장부는 저장소 밖에 둔다.

**아직 미실행:** 새 가상 계정의 영구 생성, 승인 audit UUID 런타임 주입, 신규 앱 → FastAPI → 실제 MariaDB의 로그인/핵심 3 CRUD/재조회/두 계정 격리, 실제 배포. 코드 병합이나 모의 테스트만으로 기능 VERIFIED·실제 전체 통합 완료를 주장하지 않는다.

## 후속 브라우저 검사

PR #62는 최초 독립 검토에서 로그인 전환·모집 취소 선택자 드리프트, API 클라이언트 리디렉션에 따른 자격 유출 가능성, 정리 대상 표식 검증과 세션 정리 문제를 발견했다. 해당 PR은 보완·독립 회귀·새 HEAD CI 전까지 병합하지 않는다. 나머지 검증된 PR은 이 문제와 분리해 병합했다.
