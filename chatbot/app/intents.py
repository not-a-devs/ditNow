from app.retriever.keyword import normalize

CAMPUS = "campus"

# 띄어쓰기를 뺀 표현. 'A+B'는 A와 B가 모두 들어 있으면 일치.
# 정확한 표현이 'A+B' 조합보다 우선하고, 같은 종류끼리는 위에 있는 의도가 우선한다
INTENT_KEYWORDS: dict[str, list[str]] = {
    "next_class": [
        "다음수업",
        "다음강의",
        "다음교시",
        "수업어디",
        "강의실어디",
        "수업+몇시",
        "수업+언제",
    ],
    "today_classes": ["오늘수업", "오늘강의", "오늘시간표", "내시간표", "수업시간표"],
    "remaining_credits": ["졸업+학점", "남은학점", "학점남", "졸업까지", "졸업요건", "이수학점"],
}


def classify(question: str) -> str:
    """질문의 의도를 고른다. 개인 질문 표현이 없으면 교내 정보 검색(campus)."""
    compact = normalize(question).replace(" ", "")
    # '오늘 수업 몇시에 끝나'는 '수업+몇시'(다음 수업)보다 '오늘수업'(오늘 시간표)이 맞다
    for combo in (False, True):
        for intent, keywords in INTENT_KEYWORDS.items():
            for k in keywords:
                if ("+" in k) == combo and all(part in compact for part in k.split("+")):
                    return intent
    return CAMPUS
