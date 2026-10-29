# TASK-S — 교수 화면 공유 1차 기반

상태: **PARTIAL / TESTED(모의 UOW·모의 미디어)**. 실제 화면 캡처·학생 간 WebRTC 송수신·인증·DB·실시간 broker·배포는 **NOT_RUN / 승인·환경 대기**다. FR-COURSE-006 전체를 IMPLEMENTED/VERIFIED로 표시하지 않는다.

## 근거·소유 범위·완료 조건

FR-COURSE-006, API-COURSE, RBAC-COURSE, TC-V1-COURSE-006, NFR-STREAM-001~003, NFR-SEC-002/004/005, NFR-PRIV-003, NFR-REL-001, NFR-UX-001/004를 적용한다. [기존 FRD](../02_FRD.md)의 교수 명시적 선택·학생 시청 전용·오디오/녹화 OFF 방향을 유지한다. [OPEN-006](../11_DECISION_LOG.md)의 녹화·녹음·개인정보 고지는 승인하지 않았다.

허용 경로는 `services/api/app/features/screen_sharing/`, `services/api/tests/test_screen_sharing.py`, `apps/web/src/features/screen-sharing/`와 이 문서다. 공통 인증/DB/config/lockfile/App/router/NAV는 수정하지 않는다. 공통 통합 소유자가 이후 승인된 bridge를 연결해야 한다. 실제 DB·외부 서비스·컨테이너·비용·계정은 만들지 않았으며 기존 `mvp/` 코드를 읽거나 복사하지 않았다.

이번 AC는 공급자 독립 제어·신호 서비스와 미디어 수명주기의 단위 검증이다. 원래 AC인 교수1+학생2 실제 브라우저 재생·종료/재연결·비수강생 차단은 **아직 미검증**이다.

## 기존 분반·권한 재사용

- `ClassroomActor`, `ClassroomGrant`, 기존 `ClassroomTransaction.offering/grant`를 참조한다. 신규 사용자/소속/분반 원장을 만들지 않는다.
- adapter는 같은 UOW에서 공통 active DEMO identity·현재 수강 또는 담당 교수 부여를 읽는다. 클라이언트 role/user/header나 예전 토큰의 분반을 신뢰하지 않는다.
- 한 분반에 만료되지 않은 세션은 하나이고 교수 한 명만 presenter다. 참가자는 외부로 실제 사용자 UUID 대신 해당 세션의 임시 peer UUID를 받는다. 일반 시청자는 교수와 본인 peer만 보며 다른 시청자 목록을 받지 않는다.
- 매 요청·신호 replay·수신 delivery에서 현재 양쪽 권한을 확인한다. actor→offering/session→member/claim 잠금과 CAS·unique·signal budget 갱신은 실제 DB/broker adapter의 필수 책임이다. fake RLock은 MariaDB 동시성을 증명하지 않는다.
- 교수는 세션 시작/활성화/종료·시청자 폐기, 학생은 참여/수신·자신의 ICE/recvonly 답변·나가기만 가능하다. 학생 OFFER, 학생 간 신호, 자기 자신 전달, 타 분반/다른 세대 신호는 거부한다.

## API 및 상태

export router prefix `/screen-sharing`는 기본 앱에 **미마운트**이며 기존 공통 actor dependency와 신규 서비스 dependency는 기본503이다. 공통 오류와 `Cache-Control: private, no-store`를 재사용한다.

| `/api/v1/screen-sharing` 뒤 경로 | 처리 |
| --- | --- |
| GET `/{offering_id}` | 현재 분반 권한·세션 요약, 원본 사용자 ID 없음 |
| POST `/{offering_id}/sessions` | 현재 담당 교수만 READY 세션·presenter peer 생성, 멱등 키 |
| POST `/{offering_id}/sessions/{id}/activate` | 교수의 expected_revision CAS, READY→LIVE |
| POST `/{offering_id}/sessions/{id}/end` | 소유 교수만 CAS 종료, ENDED 반복은 부활하지 않음 |
| POST `.../join`, `.../reconnect` | 현재 수강/담당 권한, 재연결 generation 증가, 멱등 키·이전 세대 차단 |
| POST `.../leave`, `.../revoke/{peer_id}` | 본인 LEFT 또는 소유 교수의 타 peer REVOKED; 폐기 peer 재가입 거부 |
| POST `.../signals` | OFFER/ANSWER/ICE를 특정 상대·세대에만 전달, 멱등 키·payload hash |
| GET `.../signals?generation=&after=&limit=` | 현재 본인의 세대별 큐·단조 cursor, stale/폐기 발신자 payload 제외 |

세션은 READY→LIVE→ENDED이며 만료는 다시 시작을 요구한다. 재연결은 generation을 올리고 이전 신호를 재생하지 않는다. 세션 생성·peer·claim 및 신호·claim은 각각 같은 UOW에서 원자 처리하며 예외 시 rollback한다. 종료/폐기된 claim은 TTL 동안 보존해 재생이 리소스를 되살리지 않게 한다.

신호는 화면 픽셀이 아니라 연결 메타데이터다. SDP/ICE에는 IP 등 민감한 연결 정보가 있을 수 있으므로 응답에만 한정하고 로그·감사·분석·영구 이력에 payload를 기록하지 않는다. 단일 video m-line과 교수 sendonly/학생 recvonly, audio/data/bidirectional 설명 거부는 현재 보수적 envelope다. 완전한 SDP 파서·네트워크 보안 인증을 대신하지 않는다.

안전한 시연 설계 기본값은 세션15분, 세션별 최대50 peer, peer별256 신호, SDP64KiB/ICE2KiB, 세션 총 payload4MiB, 수신 페이지 최대50개다. 신규 start/join/reconnect는 분반을 바꿔도 공유하는 actor별15분32회 원자 budget을 요구하며, 기존 유효 replay는 budget을 추가로 소비하지 않는다. budget·claim·세션 변경은 함께 rollback한다. 운영 보존 규정·30~40명 처리 성능 보장이 아니다. 실제 부하·표준 SDP 호환 검증 후 승인된 공급자에 맞춰 조정한다.

## 브라우저 구현과 미디어 경계

1. 공통 앱이 승인된 offering UUID를 전달한다. 서버 context에서 현재 role을 조회한다.
2. 교수는 먼저 **공유 연결 준비** 버튼으로 서버 세션을 확보한다. 이 단계에서는 캡처하지 않는다.
3. 별도 **화면 선택·공유 시작** 클릭에서 즉시 `getDisplayMedia({video:true,audio:false})`를 호출한다. API 응답을 기다린 뒤 자동 캡처하지 않는다. 권한 거절·브라우저 미지원·늦게 도착한 선택 결과를 안전하게 정리한다.
4. 영상 track 1개만 허용하고, 교수 transceiver는 sendonly/학생은 recvonly다. 외부 ICE 서버는 빈 배열이며 STUN/TURN/SFU를 임의 선택하지 않는다. audio track·data channel은 중지/종료한다.
5. SDP 설정 전 수신 ICE는 제한된 큐에 보관하고 remote description 이후 적용한다. 교수의 개별 시청자 장애·잘못된 응답은 해당 peer를 정리하고 다른 시청자·교수 캡처를 유지한다. 같은 실패 세대는 자동 재생성하지 않고 해당 시청자가 재연결해야 한다. 시청자의 교수 세대 교체는 이전 remote track·핸들러·ICE 큐를 비우며 늦은 이벤트도 거부한다. 전체 제어 권한/연결 실패·명시적 중지·공유창 ended·unmount·분반 변경은 track.stop, peer.close, video.srcObject 해제를 수행한다. API 종료 실패도 로컬 캡처 중지를 막지 않는다.
6. HTTP 신호 poll은 매번 서버 context를 재확인한다. 권한/세션/세대/만료 변경이나 연결 실패 시 미디어를 정리하며 자동 재캡처하지 않는다. 실패한 준비 요청의 같은 경로 재시도는 같은 멱등 키를 유지한다.

**중요한 미검증 경계:** 이미 성립한 P2P 미디어는 서버의 권한 레코드 변경만으로 즉시 강제 단절된다고 보장할 수 없다. 브라우저의 재검증/close는 구현했지만 악의적인 클라이언트를 포함한 즉각 폐기는 승인된 broker/SFU의 권한 검증·transport disconnect·자격 만료와 실제 다중 브라우저 검증이 필요하다. 이 조건 전 실제 수업 미디어 활성화를 완료했다고 주장하지 않는다. NAT 환경 연결·실시간 scale·모바일 캡처 지원도 보장하지 않는다.

## 공식 기술 자료

2026-10-30 확인. [W3C Screen Capture](https://www.w3.org/TR/screen-capture/)는 사용자 선택과 transient activation을 요구하며 getDisplayMedia 허가를 재사용 가능한 영구 승인으로 취급하지 않는다. [MDN getDisplayMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia)는 지원/권한 오류를 설명한다.

[W3C WebRTC](https://www.w3.org/TR/webrtc/)와 [MDN signaling](https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API/Signaling_and_video_calling)을 참고해 signaling transport를 특정 WS 제품으로 확정하지 않았다. [MDN track.stop](https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrack/stop)에서 stop 호출은 ended 이벤트를 발생시키지 않는 점을 확인해 명시적 정리도 별도로 구현했다. 이 자료는 우리 코드의 실제 브라우저 호환·교수 권한·전송 성공 증거가 아니다.

## 검증 상태

- BE 전용17개 PASS: 교수·현재 분반/identity, 타 사용자·타 분반, 생성 replay, CAS 종료/만료, 대상별 신호·학생 송출 거부, 권한 폐기 후 queued/replay 거부, reconnect 세대, control/signal bytes/count·payload 제한, rollback, 공통400/503/no-store·비밀 로그 억제·미마운트.
- FE 전용17개 PASS와 타입 검사 PASS: 모의 track/RTCPeerConnection만 사용한 직접 선택·학생 거부·오디오 거부·지연 캡처 종료·ICE 순서·recvonly·단절/peer 폐기, 개별 시청자 장애 격리·교수 세대 교체와 늦은 이벤트, UI503/상태/StrictMode/로컬 우선 중지/응답 오염 거부.
- 독립 읽기 전용 보안 리뷰에서 개별 peer 실패의 전체 송출 종료(P1), 세대 변경 시 remote track 잔류(P2), control claim 무제한(P2)을 모의 재현했고 수정·회귀를 추가했다. AI 검토는 사람의 미디어·권한 활성화 승인과 별개다.
- 실제 getDisplayMedia 프롬프트·개인 화면/음성·외부 peer·원격 DB·WS/SFU·파일 저장·운영 배포: **실행0 / NOT_RUN**.
- 전체 API/웹·정적 검사·빌드·최종 HEAD CI·독립 보안 리뷰 결과는 PR에 기록한다. 공유 NAV/router/App는 통합 소유자가 후속 갱신한다.
