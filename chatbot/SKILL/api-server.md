# SKILL: API 서버 (FastAPI)

> 대상 파일: `app/main.py`, `app/schemas.py`(API 모델), `app/config.py`

## 1. 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| `GET` | `/health` | 서버·데이터 로드 상태 확인 |
| `POST` | `/ask` | 질문 → 답변 (핵심) |
| `GET` | `/facilities` | 시설 목록 (프론트 지도 표시용) |
| `GET` | `/facilities/{id}` | 시설 상세 |
| `POST` | `/admin/reload` | JSON 데이터 다시 읽기 (`ADMIN_TOKEN` 헤더 필요) |

## 2. `/ask` 요청·응답

```jsonc
// 요청
{ "question": "정보관 어디 있어?", "user_location": { "lat": 35.16, "lng": 129.07 } }  // user_location은 선택

// 응답
{
  "answer": "정보관은 본관 맞은편에 있어요. 정문에서 걸어서 약 3분 거리입니다.",
  "sources": ["fac-info-hall"],
  "locations": [
    { "id": "fac-info-hall", "name": "정보관", "lat": 35.1662, "lng": 129.0723 }
  ],
  "found": true,
  "latency_ms": 840
}
```

- `found=false`이면 데이터에 없다는 뜻입니다. 프론트는 "관리자에게 제보하기" 같은 UI를 띄울 수 있습니다.
- `user_location`은 지금은 응답에 그대로 쓰지 않고, 이후 길찾기 기능에서 사용합니다. **로그에 저장하지 않습니다.**

## 3. 구조 규칙

- 앱 시작 시 `lifespan`에서 데이터 로드 → Retriever 생성 → LLMClient 생성, `app.state`에 보관합니다.
- 엔드포인트 함수는 얇게 유지하고, 로직은 `rag.py`의 `answer_question()`에 둡니다.
- 모든 요청·응답은 Pydantic 모델로 정의합니다.
- `question`은 1~200자 제한, 빈 문자열은 422.

## 4. React 연동

- CORS 허용 출처는 `.env`의 `CORS_ORIGINS`(쉼표 구분)에서 읽습니다.
  - 개발 기본값: `http://localhost:5173,http://localhost:3000`
- 프론트 호출 예시:
  ```js
  const res = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  const data = await res.json();
  ```

## 5. 운영 고려

- 간단한 IP당 요청 제한(분당 20회)을 미들웨어로 둡니다 — 해커톤 시연 중 LLM 비용 폭주 방지.
- 응답 시간 목표: 평균 2초 이내. 같은 질문은 메모리 캐시(TTL 10분)로 재사용합니다.
