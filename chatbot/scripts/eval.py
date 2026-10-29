"""검색·답변 품질 평가.

python scripts/eval.py              # 검색 Recall@3 (API 비용 없음)
python scripts/eval.py --with-llm   # 실제 LLM으로 환각·근거 체크 (비용 발생)
"""

import argparse
import asyncio
import json
import sys
from datetime import date, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import Settings, get_settings  # noqa: E402
from app.data_loader import load_data, load_mock_data  # noqa: E402
from app.db import init_db, make_engine  # noqa: E402
from app.llm import LLMClient, get_llm_client  # noqa: E402
from app.llm.fake_client import FakeLLMClient  # noqa: E402
from app.personal import KST  # noqa: E402
from app.prompt import NOT_FOUND_MARKER  # noqa: E402
from app.rag import answer_question  # noqa: E402
from app.retriever.keyword import KeywordRetriever  # noqa: E402
from app.schemas import CampusData  # noqa: E402
from app.student_repo import load_student  # noqa: E402

RECALL_TARGET = 0.9
SEMESTER = "2026-2"  # 목업 데이터의 이번 학기
EVAL_NOW = datetime(
    2026, 10, 26, 9, 0, tzinfo=KST
)  # 월요일 09:00 고정 (개인 질문 답이 시각에 따라 바뀜)


async def main(with_llm: bool) -> int:
    """평가를 돌리고 reports/에 결과를 남긴다. 기준 미달이면 1을 반환한다."""
    settings = get_settings()
    data = load_data(settings.data_dir)
    retriever = KeywordRetriever(list(data.facilities.values()), settings.min_score)
    llm = get_llm_client(settings) if with_llm else None
    cases = json.loads((ROOT / "tests" / "eval_questions.json").read_text(encoding="utf-8"))

    rows: list[str] = []
    recall_hits = recall_total = hallucinations = source_misses = 0
    for c in cases:
        top3 = [h.doc.id for h in retriever.search(c["question"], 3)]
        ok = any(i in top3 for i in c["expect_ids"]) if c["expect_found"] else True
        if c["expect_found"]:
            recall_total += 1
            recall_hits += ok
        note = ""
        if llm is not None:
            res = await answer_question(
                c["question"], retriever=retriever, llm=llm, data=data, top_k=settings.top_k
            )
            # 모르는 걸 모른다고 밝혔으면 문의처를 덧붙여도 환각이 아니다
            if not c["expect_found"] and NOT_FOUND_MARKER not in res.answer:
                hallucinations += 1
                note = f"환각: {res.answer}"
            elif c["expect_found"] and not set(c["expect_ids"]) & set(res.sources):
                source_misses += 1
                note = f"근거 누락: {res.sources} / 답변: {res.answer.replace(chr(10), ' ')}"
        mark = "✅" if ok else "❌"
        expect = ", ".join(c["expect_ids"])
        rows.append(f"| {mark} | {c['question']} | {expect} | {', '.join(top3)} | {note} |")

    personal_rows, intent_ok, personal_ok, mismatches = await _eval_personal(
        llm, retriever, data, settings
    )
    n_personal = len(personal_rows)

    recall = recall_hits / recall_total if recall_total else 1.0
    intent_acc = intent_ok / n_personal if n_personal else 1.0
    summary = [
        f"- Recall@3: **{recall:.2f}** ({recall_hits}/{recall_total}, 목표 {RECALL_TARGET})",
        f"- 개인 질문 의도 정확도: **{intent_acc:.2f}** ({intent_ok}/{n_personal}, "
        f"목표 {RECALL_TARGET})",
        f"- 개인 질문 통과: {personal_ok}/{n_personal}",
    ]
    if llm is not None:
        summary += [
            f"- 환각: **{hallucinations}건** (목표 0)",
            f"- 근거 누락: {source_misses}건",
            f"- 개인 질문 숫자·장소 불일치: **{mismatches}건** (목표 0)",
        ]
    report = "\n".join(
        [
            f"# 평가 결과 {date.today():%Y-%m-%d}",
            "",
            *summary,
            "",
            "## 교내 정보",
            "",
            "| | 질문 | 기대 | 검색 상위 3 | LLM |",
            "|---|---|---|---|---|",
            *rows,
            "",
            f"## 개인 질문 (기준 시각 {EVAL_NOW:%Y-%m-%d %a %H:%M} KST)",
            "",
            "| | 학번 | 질문 | 의도 | 근거 | 확인 |",
            "|---|---|---|---|---|---|",
            *personal_rows,
            "",
        ]
    )
    out = ROOT / "reports" / f"eval_{date.today():%Y%m%d}{'_llm' if llm else ''}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print("\n".join(summary), f"\n→ {out.relative_to(ROOT)}")
    return int(recall < RECALL_TARGET or intent_acc < RECALL_TARGET or hallucinations or mismatches)


async def _eval_personal(
    llm: LLMClient | None, retriever: KeywordRetriever, data: CampusData, settings: Settings
) -> tuple[list[str], int, int, int]:
    """개인 질문 평가. LLM이 없으면 FakeLLMClient로 의도·근거·로그인 처리만 본다.

    개발 DB를 건드리지 않도록 data/mock을 시드한 SQLite 메모리 DB에서 학생을 읽는다.
    """
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine, load_mock_data(settings.mock_dir, data))
    db = async_sessionmaker(engine)()
    cases = json.loads((ROOT / "tests" / "eval_personal.json").read_text(encoding="utf-8"))
    rows: list[str] = []
    intent_ok = passed = mismatches = 0
    # needs_llm: 키워드 규칙에 없어 LLM 분류가 있어야 맞힐 수 있는 질문 (LLM 평가에서만 센다)
    cases = [c for c in cases if llm is not None or not c.get("needs_llm")]
    for c in cases:
        bundle = await load_student(db, c["student_id"], SEMESTER) if c["student_id"] else None
        res = await answer_question(
            c["question"],
            retriever=retriever,
            llm=llm or FakeLLMClient(),
            data=data,
            student=bundle[0] if bundle else None,
            student_data=bundle[1] if bundle else None,
            now=EVAL_NOW,
        )
        problems = []
        if res.intent != c["expect_intent"]:
            problems.append(f"의도 {res.intent}")
        else:
            intent_ok += 1
        if bundle is None and not res.need_login:
            problems.append("로그인 요구 안 함")
        if c["expect_ids"] and not set(c["expect_ids"]) & set(res.sources):
            problems.append(f"근거 {res.sources}")
        # 'A|B'는 같은 뜻의 다른 표기 (예: 10:00|10시)
        missing = [t for t in c["expect_text"] if not any(a in res.answer for a in t.split("|"))]
        if llm is not None and missing:
            mismatches += 1
            problems.append(f"답변에 {missing} 없음")
        if llm is not None and problems:
            problems.append(f"답변: {res.answer.replace(chr(10), ' ')}")
        passed += not problems
        mark = "✅" if not problems else "❌"
        rows.append(
            f"| {mark} | {c['student_id'] or '(비로그인)'} | {c['question']} | {res.intent} "
            f"| {', '.join(res.sources)} | {'; '.join(problems)} |"
        )
    await db.close()
    await engine.dispose()
    return rows, intent_ok, passed, mismatches


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-llm", action="store_true", help="실제 LLM으로 답변까지 평가")
    sys.exit(asyncio.run(main(parser.parse_args().with_llm)))
