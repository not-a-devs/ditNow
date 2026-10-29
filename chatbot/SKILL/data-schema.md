# SKILL: 데이터 스키마 (JSON)

> 대상 파일: `data/*.json`, `app/schemas.py`, `app/data_loader.py`

## 1. 원칙

- 데이터는 **종류별로 파일을 나눕니다** (`facilities.json`, `schedules.json`, `faq.json` …).
- 모든 항목은 **고유한 `id`** 를 가집니다. 형식: `{종류}-{영문슬러그}` (예: `fac-info-hall`)
- 검색 품질을 위해 **`aliases`(별칭)** 를 적극적으로 채웁니다. 학생들이 실제로 부르는 이름을 넣으세요.
- 모든 항목은 공통 필드 `id`, `type`, `name`, `aliases`, `description`, `updated_at`을 가집니다.

## 2. 파일별 스키마

### facilities.json — 건물·시설

```json
[
  {
    "id": "fac-info-hall",
    "type": "facility",
    "name": "정보관",
    "aliases": ["정보동", "컴소과 건물", "IT관"],
    "category": "building",
    "description": "컴퓨터소프트웨어과 강의실과 실습실이 있는 건물입니다.",
    "location": {
      "lat": 35.1662,
      "lng": 129.0723,
      "floor": null,
      "landmark": "본관 맞은편, 정문에서 도보 약 3분"
    },
    "open_hours": "평일 08:00~22:00",
    "contains": ["fac-info-hall-lab1"],
    "tags": ["강의실", "실습실"],
    "updated_at": "2026-10-29"
  }
]
```

### schedules.json — 운영시간·학사일정

```json
[
  {
    "id": "sch-cafeteria",
    "type": "schedule",
    "name": "학생식당 운영시간",
    "aliases": ["학식", "식당 시간"],
    "description": "학기 중 평일 중식 11:30~13:30, 석식 17:00~18:30. 주말 휴무.",
    "related_ids": ["fac-cafeteria"],
    "valid_from": "2026-09-01",
    "valid_to": "2026-12-20",
    "updated_at": "2026-10-29"
  }
]
```

### faq.json — 자주 묻는 질문

```json
[
  {
    "id": "faq-wifi",
    "type": "faq",
    "name": "교내 와이파이 접속 방법",
    "aliases": ["와이파이", "wifi", "인터넷"],
    "question": "학교 와이파이 어떻게 연결해요?",
    "answer": "…",
    "related_ids": [],
    "updated_at": "2026-10-29"
  }
]
```

## 3. Pydantic 모델 규칙 (`app/schemas.py`)

```python
from pydantic import BaseModel, Field

class Location(BaseModel):
    lat: float
    lng: float
    floor: int | None = None
    landmark: str | None = None

class BaseDoc(BaseModel):
    id: str
    type: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    updated_at: str

    def to_search_text(self) -> str:
        """검색·임베딩에 사용할 텍스트를 만든다."""
        return " ".join([self.name, *self.aliases, self.description])

class Facility(BaseDoc):
    category: str
    location: Location
    open_hours: str | None = None
    contains: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
```

- 각 하위 모델은 `to_search_text()`를 필요에 따라 오버라이드합니다.
- LLM에 넘길 때는 `to_context()` 메서드로 **사람이 읽기 좋은 짧은 텍스트**를 만듭니다.

## 4. data_loader.py 규칙

- 서버 시작 시 `data/` 아래 JSON을 모두 읽어 `dict[str, BaseDoc]` (id → 문서)로 보관합니다.
- 검증 실패 시 **파일명 + 항목 id + 에러 내용**을 출력하고 서버 시작을 중단합니다.
- `id` 중복, `related_ids`/`contains`가 존재하지 않는 id를 가리키는 경우도 에러로 처리합니다.

## 5. 데이터 추가 체크리스트

- [ ] `id` 형식과 중복 확인
- [ ] 학생들이 실제로 쓰는 별칭 3개 이상
- [ ] 위치 정보가 있으면 `landmark`(말로 설명하는 위치)도 함께
- [ ] `updated_at` 갱신
- [ ] `pytest tests/test_data.py` 통과
