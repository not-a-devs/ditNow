# TASK-W — 강의실 화면 요청·초안 경쟁 조건 수정

상태: **PARTIAL / TESTED**(프런트 강의실 모듈과 Vitest/jsdom 범위). 실제 브라우저·운영 인증·MariaDB·공통 라우터 연결은 **NOT_RUN**이며 VERIFIED로 표시하지 않는다.

## 범위

수정 파일: `apps/web/src/features/classrooms/index.tsx`, `apps/web/src/features/classrooms/index.test.tsx`, 이 문서. 백엔드·공통 API 클라이언트·테스트 setup·라우터·OpenAPI·패키지·DB는 변경하지 않았다. 관련 기준은 [TASK-G-CLASSROOMS](TASK_CLASSROOMS_IMPLEMENTATION.md)의 FR-COURSE-004/005, NFR-REL-001/003, NFR-SEC-002(401/403 후 개인 내용 제거)이며 FR·DEC는 바꾸지 않는다.

## 처음 관찰한 실패

Windows에서 여러 모듈 테스트가 병렬로 도는 전체 웹 회귀에서 `classrooms/index.test.tsx`의 409/401/403 경고 기대와 그다음 unmount signal 테스트가 반복해서 실패했다. 이 파일만 따로 돌리면 9개가 모두 PASS였다(이 작업 시작 시 다시 실행해도 9 PASS).

## 원인 (실제로 재현함)

1. **늦은 마운트 effect가 입력한 초안을 덮어씀.** `AssignmentCard`의 `useEffect(() => setText(submission?.text ?? ''), [submission?.revision])`는 마운트할 때도 실행된다. 부하가 걸리면 React 스케줄러가 워크스페이스 커밋과 passive effect 실행을 서로 다른 태스크로 나눈다. 테스트(또는 사용자)가 화면이 보인 직후 입력하면 대기 중이던 effect가 그 뒤에 `''`를 써 넣는다. 그러면 버튼이 비활성화되어 제출 요청이 나가지 않고, 409/401/403 경고도 나타나지 않는다.
   - 결정적 재현: 원래 코드에서 커밋 직후(MutationObserver 마이크로태스크)에 입력하는 시험과 `performance.now`로 스케줄러 양보를 강제하는 시험 **2건이 모두 FAIL**했다(값이 `''`로 바뀜). 임시 시험 파일은 삭제했고, 앞의 방식을 회귀 테스트로 남겼다.
2. **소비되지 않은 mock 응답이 다음 테스트로 샘.** 공통 setup이 `requestData` mock을 리셋하지 않는다. 위 1번 때문에 제출 요청이 나가지 않으면 `mockRejectedValueOnce`가 큐에 남는다. 그러면 다음 테스트의 첫 목록 요청이 남은 응답을 받아 연쇄 실패가 나고, unmount 테스트의 `mockImplementationOnce`도 밀려 signal이 비게 된다. 테스트 파일에 `beforeEach(mockReset)`을 넣어 격리했다. 공통 setup은 root 소유라 손대지 않았다.
3. **대체된 쓰기의 결과·오류가 새 화면에 반영될 수 있음.** 페이지 경고의 "목록 다시 확인"은 쓰기 중에도 누를 수 있다. 그런데 `load()`가 진행 중인 쓰기를 취소하지 않아서, 이전 제출 응답이 다시 연 워크스페이스에 병합되고 `busy`·오류도 새 화면에 남을 수 있었다. (원래 코드에서 이 시험이 실패하는지는 아래 결과에 기록했다.)

## 수정

- 초안은 `{revision, text}` 상태로 관리한다. 서버 revision이 실제로 바뀔 때만 렌더 중에 교체하고, 마운트 effect는 없앴다. 최초 제출은 여전히 `expected_revision: 0`이며 이후에는 서버 revision을 쓴다.
- `load()`와 목록 돌아가기는 진행 중인 쓰기를 abort하고 `busy`를 해제한다. abort된 쓰기는 `SupersededWrite`로 버리고 결과 병합, 401/403 처리, 오류 표시를 하지 않는다. 실제 요청 timeout(`CANCELLED`)이나 서버 오류는 지금처럼 표시한다.
- timeout 늘리기, 재시도, skip, 동시성 끄기는 하지 않았다.

## 남은 게이트

- 실제 브라우저·느린 기기에서의 입력 경쟁, 실서버 abort 동작: NOT_RUN.
- 공통 `src/test/setup.ts`에 전역 mock 리셋을 넣을지는 root가 결정한다(다른 모듈에도 같은 누수 위험이 있을 수 있음).
- 운영 인증·수강 원장·MariaDB 연결은 TASK-G-CLASSROOMS의 BLOCKED 상태를 그대로 유지한다.
