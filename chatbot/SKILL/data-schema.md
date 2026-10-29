# SKILL: 데이터 스키마 (JSON)

> 대상 파일: `data/*.json`, `app/schemas.py`, `app/data_loader.py`

## 1. 원칙

- 데이터는 **종류별로 파일을 나눕니다**. 현재: `facilities.json`(검색 대상), `buildings.json`(건물 위치).
- 학생 개인 데이터는 MariaDB에 있고 `data/mock/*.json`은 그 시드입니다 → `SKILL/database.md`.
- 모든 시설 항목은 **고유한 `id`** 를 가집니다. 형식: `{접두어}_{영문슬러그}`
  - `dept_` 학과사무실 · `admin_` 행정부서 · `fac_` 편의시설·식당 · `bld_` 건물
- 검색 품질을 위해 **`aliases`(별칭)** 를 적극적으로 채웁니다. 학생들이 실제로 부르는 이름을 넣으세요.
- 한 글자 별칭(`밥`, `약`)은 질문에서 **띄어쓴 단어와 정확히 같을 때만** 매칭됩니다(오탐 방지).

## 2. 파일별 스키마

### facilities.json — 검색 대상 문서

```json
{
  "id": "dept_cs",
  "category": "학과사무실",
  "name": "컴퓨터소프트웨어과",
  "aliases": ["컴소과", "컴공"],
  "building": "미래관",
  "building_id": "mirae",
  "floor": null,
  "room": "301호",
  "phone": "051-860-0000",
  "hours": null,
  "note": null,
  "text": "컴퓨터소프트웨어과 학과사무실은 미래관 301호에 있습니다."
}
```

- `category`: `건물` | `학과사무실` | `행정부서` | `편의시설` | `식당`
- `building_id`: `buildings.json`의 `building_id`를 가리키거나 `null`(위치 미상·온라인)
- `text`: 한 문장 이상의 설명. LLM 컨텍스트의 핵심이므로 **필수**입니다.
- `floor`, `room`, `phone`, `hours`, `note`는 모르면 `null`

### buildings.json — 건물 위치

```json
{
  "building_id": "mirae",
  "name": "미래관",
  "aliases": [],
  "address": "부산광역시 부산진구 양지로 54 (47230)",
  "lat": null,
  "lng": null
}
```

- `lat`/`lng`가 채워진 건물만 `/ask` 응답의 `locations`에 좌표로 나갑니다(현재 전부 `null`).

## 3. Pydantic 모델 (`app/schemas.py`)

- `Facility`, `Building`, 둘을 묶은 `CampusData`
- `Facility.to_search_text()` — 키워드 검색용 텍스트
- `Facility.to_context()` — LLM에 넘길 **사람이 읽기 좋은 짧은 텍스트**

## 4. data_loader.py 규칙

- 서버 시작 시 `load_data(data_dir)`가 두 파일을 읽어 `CampusData`(id → 문서 dict)로 보관합니다.
- 검증 실패 시 **파일명 + 항목 id + 에러 내용**을 담은 `DataError`를 던져 서버 시작을 중단합니다.
- `id` 중복, `building_id`가 없는 건물을 가리키는 경우도 에러입니다.

## 5. 데이터 추가 체크리스트

- [ ] `id` 형식과 중복 확인
- [ ] 학생들이 실제로 쓰는 별칭 3개 이상
- [ ] `building_id`가 `buildings.json`에 있는지
- [ ] `tests/eval_questions.json`에 질문 2~3개 추가
- [ ] `pytest tests/test_data.py` 통과
