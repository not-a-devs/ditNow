# TASK-I — 공개 대학·학과 안내 조회 1차 구현

상태: **PARTIAL / TESTED**. 공개 원문을 근거로 작성한 자체 요약의 목록·검색·분류·상세 조회를 실제 FastAPI와 신규 웹 내비게이션에 연결했다. 로컬 실제 HTTP·브라우저로 검증했으며 운영 배포는 미실행이다. FR 전체를 VERIFIED로 표시하지 않는다.

## 요구사항·소유 범위

FR-WEB-001~004, FR-DEPT-007/008, API-PUBLIC, RBAC-WEB/DEPT, TC-V1-WEB-001~004, TC-V1-DEPT-007/008의 공개 읽기 부분을 구현한다. NFR-UX-001/003/005, NFR-DATA-003, NFR-SEC-004/005/007, NFR-REL-005와 연결한다.

기능 수정 소유: `services/api/app/features/public_campus/`, `services/api/tests/test_public_campus.py`, `apps/web/src/features/public-campus/`, 이 문서. 통합 소유자가 공유 라우터·App·내비·아이콘·공개 OpenAPI·생성 타입·NAV를 별도로 등록했고 기능 작성자가 그 변경을 독립 읽기 검토했다. 공통 인증·DB·패키지·마이그레이션은 수정하지 않는다. 기존 mvp의 생성 타입 갱신은 역사적 CI 드리프트 방지를 위한 것이며 코드를 신규 앱에 재사용하지 않았다.

## 공개 스냅샷과 출처

원장: `snapshot.json`의 버전 `public-campus-2026-10-30-v1`, 7개 자체 편집 안내. 전체 대학·학과 콘텐츠를 모두 수집한 목록이 아니다. 이미지·영상·실명 직원/학생·기사 전문을 수집하거나 복제하지 않았다.

| 범위 | 자체 요약 | 공식 근거 |
| --- | --- | --- |
| WEB-001 | 기관 구분과 학사 업무 범주 | [기구소개](https://www.dit.ac.kr/kr/index.php?pCode=orgn) |
| WEB-002 | VR 공간별 구분과 방문 안내의 정보 범위 | [캠퍼스 VR](https://www.dit.ac.kr/kr/index.php?pCode=compusvr) |
| WEB-003 | 공개 제도·절차·서식의 분류 | [정보공개 안내](https://www.dit.ac.kr/kr/index.php?pCode=information0101) |
| WEB-004 | 홍보 갤러리의 목록·검색 구성 | [포토·영상 갤러리](https://www.dit.ac.kr/kr/index.php?pCode=photogallery) |
| DEPT-007 | 컴퓨터소프트웨어과 학습 방향·메뉴 범위 | [학과 소개](https://www.dit.ac.kr/cs/index.php?pCode=MN4000016), [학과 홈](https://www.dit.ac.kr/cs/) |
| DEPT-008 | 공지·활동의 구분, 목록 검색·첨부 표시 | [학과 공지](https://www.dit.ac.kr/cs/index.php?pCode=MN4000038) |

확인일은 **2026-10-30 KST에 공식 페이지의 웹 도구 반환본을 확인한 날짜**다. 도구가 과거 수집본을 반환할 수 있으므로 원문 최종 수정일·실시간 최신성으로 표시하지 않는다. 각 레코드에 URL·확인일·확인 설명·범위·기능 존재 VERIFIED/처리 규칙 PARTIAL/최신성 UNKNOWN을 따로 저장한다. 내용은 `EDITORIAL_PUBLIC_SUMMARY`이며 학교 공식 게시물이나 현재 운영 원장과 동일하다고 표시하지 않는다.

조회 전용 공개 콘텐츠는 v1 FRD의 공통 완료 계약에 따라 출처·확인일·개정을 갖춘 스냅샷을 조회 원장으로 사용할 수 있다. **이 공개 읽기 범위에 한해 MariaDB=N_A**다. 콘텐츠 작성·승인·변경 이력·학과 권한 관리·뉴스 동기화는 미구현이며 해당 FR 전체의 DB 요구를 제거하지 않는다.

## API와 사용자 흐름

`router`는 `/public-campus` 상대 prefix를 export하고 통합 담당자가 `/api/v1` 아래 한 번 등록했다. 기본 앱 OpenAPI를 실제 라우터에서 재생성했으며 신규 웹 `/app/information` 메뉴가 해당 HTTP API를 호출한다.

| 메서드·경로 | 입력·출력 | 예외 |
| --- | --- | --- |
| GET `/public-campus` | q 최대200자, category, site, offset>=0, limit1~50 → data.items/total/offset/limit/snapshot_version/notice | 부정 입력400, 스냅샷 로드·검증 실패503 |
| GET `/public-campus/{record_id}` | 영소문자/숫자/하이픈 ID → 자체 요약·본문 단락·출처·관련 FR | 잘못된 ID400, 미존재404 |
| POST/PUT/PATCH/DELETE | 제공하지 않음 | 등록된 조회 경로에 쓰기405 |

검색은 NFKC·소문자·공백 정규화 후 제목·요약·태그·자체 본문에 검색어 AND 조건을 적용한다. ID 정렬로 페이지를 안정화한다. 사이트 필터는 대학 홈페이지/컴퓨터소프트웨어과 공개 출처 구분이며 사용자의 소속이나 로그인 역할이 아니다.

신규 화면: 최초 목록 요청 → 검색/주제/출처 선택 → 자체 카드 → 상세 본문 → 근거·확인 범위·선택적인 공식 원문. 로딩/빈 결과/오류·재시도/입력 제한/요청 취소를 제공한다. 원문 링크만 나열하는 외부 런처가 아니다. HTML을 실행하지 않고 React 텍스트로 렌더링하며 응답 구조와 공식 URL 범위를 런타임 검증한다. 과거 chatbot 시설 검색은 `/ai/campus/search`로 유지하고 이 안내 목록의 별도 namespace와 목적을 구분한다.

## 권한·보안·남은 업무

공개 조회만 제공하며 개인 신원·학적·DB 자격 정보가 없다. 요청 시 외부 URL을 가져오지 않아 SSRF·뉴스 크롤러 경로를 만들지 않는다. 출처는 HTTPS·학교 공식 호스트와 공개 경로를 제한하고 자격 증명·fragment·비허용 query를 거부한다.

미구현: 홍보담당/학과담당 콘텐츠 CRU/승인·보관·감사·개정 업무, 전체 학과·교수·조직 원장, 보호 첨부/이미지 라이선스, 뉴스 피드·수정 동기화, 실제 정보공개 청구, VR/지도 자체 렌더링, 소속별 편집 권한, 공지 자동 배포. 정책·직원 권한·공통 DB가 필요한 쓰기는 BLOCKED이며 화면 버튼만으로 대신 구현하지 않는다.

## 자동 수용 검사

- TC-I-001: 7개 스냅샷이 6개 FR의 읽기 범위를 참조하고 URL/확인일/분리된 검증 수준을 갖는다.
- TC-I-002: Unicode/공백 정규화 검색, 주제/출처 필터, 안정 페이지, 빈 결과·다중 필터·offset 경계를 검사한다.
- TC-I-003: 자체 상세 본문/근거 조회, 미존재404, 입력400, 쓰기405와 공통 응답 형식을 검사한다.
- TC-I-004: 중복 ID·확인일 모순·출처 사이트 불일치·유해/비허용 URL을 거부한다.
- TC-I-005: FE 카드/검색/필터/자체 상세·텍스트 렌더링·출처 한계·원문 링크·빈/오류·취소·응답 오염을 검사한다.

2026-10-30 최신 main `3c0a0bd` 및 공유 등록을 반영한 Python 신규22개 및 전체419개 PASS, Ruff70개 포맷/정적 검사 PASS. 신규 웹 npm ci(취약점0), 타입 검사·전체148개 Vitest(이 모듈7개 및 통합 App 연결1개 포함)·빌드·OpenAPI 타입 드리프트 검사 PASS. `python -m app.export_openapi --check` PASS. 검증 중 잘못 입력한 `app.openapi` 모듈 명령은 존재하지 않아 실패했고 실제 제공되는 `app.export_openapi`로 정정하여 비교했다. 에이전트 설정·92개 진행표 검사·git diff 검사 PASS. 최종 PR HEAD의 원격 CI는 Push 후 확인한다.

별도 Codex 읽기 전용 리뷰에서 기능 소스·7개 공개 근거를 재확인하고 BE22개·FE7개·타입 검사를 직접 통과했다. 중요 차단 finding은 없었다. 향후 콘텐츠 편집을 도입할 때 `pCode` 값도 현재 공개 항목 allowlist로 좁히는 비차단 권고가 남았다. 현재는 고정 스냅샷이며 요청 시 외부 fetch와 쓰기가 없다. 이 AI 리뷰는 사람의 공식 승인이 아니다.

통합 소유자가 작성한 공유 라우터·App·내비·아이콘·GET 전용 OpenAPI 테스트를 기능 작성자가 독립 읽기 검토했다. 빈 결과 문구 불일치를 수정한 뒤 중요 차단 finding은 없었다.

실제 로컬 Uvicorn → 신규 Vite 웹을 Chromium 390px/1280px에서 검증했다. 한글 검색·학과/출처 필터·7개 목록의 페이지 이동·자체 상세 본문·출처 링크/한계 표시·빈 결과·주입한 503의 안전한 오류/재시도·실제 미존재404/쓰기405·명시적 허용 origin CORS/미허용 origin 거부가 PASS였다. 두 폭의 문서 너비는 각각 390/1280px이며 pageerror는 없었다. 목록·상세 스크린샷 4개를 직접 확인했다. 모바일 상세 제목 초점이 sticky 헤더에 가리는 문제는 해당 제목의 scroll margin으로 수정하고 제목 top88.33px > 헤더 bottom66px을 실제 브라우저로 재검증했다. 검사 스크립트와 스크린샷은 저장소 밖 임시 도구 위치에 있으며 개인정보를 포함하지 않는다. 임시 서버는 검증 후 종료했다.

운영 DB·실제 학교 원장·인증/편집 권한·운영 배포는 NOT_RUN이며 공개 읽기 범위 이외의 6개 FR 업무는 계속 PARTIAL/BLOCKED다.
