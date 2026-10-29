from app.retriever.keyword import normalize

CAMPUS = "campus"

# 띄어쓰기를 뺀 표현. 위에 있는 의도가 우선한다 ('다음 수업 시간표' → next_class)
INTENT_KEYWORDS: dict[str, list[str]] = {
    "next_class": ["다음수업", "다음강의", "다음교시", "수업어디", "강의실어디"],
    "today_classes": ["오늘수업", "오늘강의", "오늘시간표", "내시간표", "수업시간표"],
    "remaining_credits": ["졸업학점", "남은학점", "학점남", "졸업까지", "졸업요건", "이수학점"],
}


def classify(question: str) -> str:
    """질문의 의도를 고른다. 개인 질문 표현이 없으면 교내 정보 검색(campus)."""
    compact = normalize(question).replace(" ", "")
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(k in compact for k in keywords):
            return intent
    return CAMPUS
