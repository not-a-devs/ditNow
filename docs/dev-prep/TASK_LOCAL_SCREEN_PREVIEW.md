# TASK-LOCAL-SCREEN-PREVIEW — 교수 로컬 화면 미리보기 (FR-COURSE-006 부분)

상태: **PARTIAL / DORMANT / 테스트 작성됨(NOT_RUN)**. 라우터·App에 mount하지 않았다. 실제 캡처·장치·브라우저 호환·네트워크 송출·인증·DB는 검증하지 않았다. FR-COURSE-006 전체를 IMPLEMENTED/VERIFIED로 표시하지 않는다.

## TASK / 범위
- 교수가 **직접 클릭**으로 고른 화면을 **자기 브라우저 안에서만** 미리보는 FE 컴포넌트.
- 기존 `media.ts`의 `MediaRoom`을 수정 없이 재사용: `presenter=true`, no-op `send`, `chooseScreen()`만 호출. `sync`/`receive` 미호출 → `RTCPeerConnection`·ICE·signal·업로드·송출·녹화 없음.
- 교수 권한 부여·수업 세션 인증을 흉내 내지 않는다. `sessionGeneration`은 정리 경계(key)로만 쓰며 권한 근거가 아니다.

| 구분 | FR-COURSE-006 요구 | 이 작업 |
|---|---|---|
| 교수 명시적 화면 선택, 자동 캡처 금지 | 필요 | **구현**(클릭 핸들러 안 await 전 `getDisplayMedia`) |
| 브라우저 미지원·권한 거절·공유 중지 예외 | 필요 | **구현**(보안 컨텍스트·기능 감지·모바일 미지원, 고정 안내) |
| 오디오·녹화 기본 OFF | 필요 | **유지**(`audio:false`, 오디오 트랙 유입 시 전부 중지) |
| 학생 시청·실시간 송출·SFU/재연결 | 필요 | **미구현** |
| 수강생 아닌 계정 거부·토큰 만료 | 필요 | **미구현**(BE/인증 미연결) |
| 교수 1·학생 2+ 실기기 AC | 필요 | **NOT_RUN** |

## FR / NFR 적용
- FR-COURSE-006(부분): 명시적 선택, 미지원/거절/중지 처리, 오디오 OFF.
- NFR-PRIV/SEC: 원문 오류·장치명 비노출, 로그 출력 없음, storage 미사용, 외부 전송 없음.
- NFR-REL/UX: 중지·트랙 종료·unmount·세대 변경 시 트랙과 `onended` 정리, StrictMode 안전, 동기 busy ref로 중복 프롬프트 방지, 항상 한국어 로컬 전용 고지.

## 계약 (FE only, API 없음)
- `export default function LocalScreenPreview({ sessionGeneration?: number })`
- `export function previewSupported(): boolean` — `window.isSecureContext` && 비모바일(`userAgentData.mobile`, UA `Android|iPhone|iPad|iPod|Mobile`) && `navigator.mediaDevices.getDisplayMedia` 함수.
- 상태: `IDLE | CHOOSING | PREVIEW | STOPPED | ENDED | DENIED`. 비디오: `autoPlay muted playsInline`, `srcObject` attach/clear.
- 신규 BE·엔드포인트·`requestData` 호출 없음 → default503/CAS/idempotency/역할·scope 검사는 **해당 없음**(서버 상호작용 없음).

## TC (작성만, 실행 안 함)
`apps/web/src/features/screen-sharing/LocalScreenPreview.test.tsx` (mock `getDisplayMedia`/`RTCPeerConnection`/`fetch`, 실캡처·장치·네트워크 없음):
마운트 무캡처·고지 / 클릭 동기 호출 `{video:true,audio:false}`·중지 정리 / 중복 클릭 1회 / 거절 고정 안내·재시도 / 오디오 유입 거부 / 미지원 4종(비보안·API 없음·모바일 UA·userAgentData) / 트랙 ended / unmount 정리 / unmount 후 늦은 캡처 중지 / 선택 중 중지 후 늦은 캡처 / StrictMode / sessionGeneration 변경 정리 / `sync`·`receive`·`RTCPeerConnection`·`fetch` 미호출.

## 테스트 명령 (NOT_RUN — Codex 실행·리뷰 대상)
- `cd apps/web && npx vitest run src/features/screen-sharing/LocalScreenPreview.test.tsx` — NOT_RUN
- `cd apps/web && npx vitest run src/features/screen-sharing` (기존 media/index 회귀) — NOT_RUN
- 타입체크/빌드 — NOT_RUN

## 가정 / 블로커
- 가정: `styles.module.css`의 `page`·`notice` 클래스 재사용(공유 파일 미수정). 테스트 setup의 jest-dom·자동 cleanup은 기존 `index.test.tsx` 패턴과 동일하다고 가정.
- 가정: jsdom은 `srcObject`를 구현하지 않아 expando로 검증한다. 실제 브라우저 재생은 미검증.
- 한계: iPadOS 데스크톱 UA는 모바일로 감지되지 않을 수 있다(그 경우 기능 감지에 의존).
- 블로커: 실제 시청·송출(SFU/브로커), 인증·수강 권한, mount 위치 결정은 승인·환경 대기. 실제 인증/DB/승인 주장 없음. 데이터 저장 없음(프로세스 메모리 상태도 React state뿐, 새로고침 시 소실).

## 파일 소유
- `apps/web/src/features/screen-sharing/LocalScreenPreview.tsx` (신규)
- `apps/web/src/features/screen-sharing/LocalScreenPreview.test.tsx` (신규)
- `docs/dev-prep/TASK_LOCAL_SCREEN_PREVIEW.md` (신규)
- `media.ts`·라우터·공유 파일·BE 미수정.

## 실제 검증 및 작성 주체 (2026-10-30)

- Claude Code 2.1.314의 제한 세션 1개가 위 신규 3파일을 작성했다. 허용 도구는 Read/Grep/Glob/Edit/Write이며 Bash·MCP·Git·실제 캡처·DB·네트워크 도구를 사용하지 않았다. Claude는 테스트를 실행하지 않았다. Codex가 소스 전체를 독립적으로 읽고 아래 명령을 실행했다.
- Claude가 일부 진입 지침 문서를 완독하지 않았다고 보고하여 Codex가 NAV/AGENTS/CLAUDE/runbook과 적용 스킬·관련 요구사항을 확인했다. 전체 지침을 Claude가 읽었다고 주장하지 않는다.
- `npm ci --ignore-scripts --offline --prefix apps/web`: PASS, audit 0.
- 신규 `LocalScreenPreview.test.tsx`: 15 PASS. 기존 화면 공유 회귀를 포함한 `vitest run src/features/screen-sharing`: 32 PASS.
- 신규 웹 `typecheck`, `build`, `git diff --check`: PASS.
- 관련 NFR: NFR-PRIV-002(최소 수집), NFR-PRIV-003(불필요 로그 없음), NFR-UX-001~005(상태·키보드·오류·시연 경계). 관련 전체 수용 테스트는 TC-V1-COURSE-006이며 교수 1/학생 2 원격 시청은 이 로컬 미리보기로 충족되지 않는다.
- 상태는 로컬 미리보기 코드에 한해 TESTED, 전체 FR은 PARTIAL이다. 실제 장치 캡처·원격 시청·운영 권한·DB·배포는 NOT_RUN. NAV/App 연결은 공통 소유자의 후속 작업이다.
