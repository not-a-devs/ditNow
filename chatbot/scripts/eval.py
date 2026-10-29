"""검색·답변 품질 평가.

python scripts/eval.py              # 검색 Recall@3 (API 비용 없음)
python scripts/eval.py --with-llm   # 실제 LLM으로 환각·근거 체크 (비용 발생)
"""

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.data_loader import load_data  # noqa: E402
from app.llm import get_llm_client  # noqa: E402
from app.rag import answer_question  # noqa: E402
from app.retriever.keyword import KeywordRetriever  # noqa: E402

RECALL_TARGET = 0.9


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
            if not c["expect_found"] and res.found:
                hallucinations += 1
                note = f"환각: {res.answer}"
            elif c["expect_found"] and not set(c["expect_ids"]) & set(res.sources):
                source_misses += 1
                note = f"근거 누락: {res.sources}"
        mark = "✅" if ok else "❌"
        expect = ", ".join(c["expect_ids"])
        rows.append(f"| {mark} | {c['question']} | {expect} | {', '.join(top3)} | {note} |")

    recall = recall_hits / recall_total if recall_total else 1.0
    summary = [f"- Recall@3: **{recall:.2f}** ({recall_hits}/{recall_total}, 목표 {RECALL_TARGET})"]
    if llm is not None:
        summary += [f"- 환각: **{hallucinations}건** (목표 0)", f"- 근거 누락: {source_misses}건"]
    report = "\n".join(
        [
            f"# 평가 결과 {date.today():%Y-%m-%d}",
            "",
            *summary,
            "",
            "| | 질문 | 기대 | 검색 상위 3 | LLM |",
            "|---|---|---|---|---|",
            *rows,
            "",
        ]
    )
    out = ROOT / "reports" / f"eval_{date.today():%Y%m%d}{'_llm' if llm else ''}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print("\n".join(summary), f"\n→ {out.relative_to(ROOT)}")
    return int(recall < RECALL_TARGET or hallucinations > 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-llm", action="store_true", help="실제 LLM으로 답변까지 평가")
    sys.exit(asyncio.run(main(parser.parse_args().with_llm)))
