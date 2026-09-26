"""Error analysis for product cases on the DEV split only (test split is held out).

Usage (from backend/): uv run python ../evaluation/analyze_errors.py ../evaluation/datasets/eval-v1.jsonl
"""

import asyncio
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from recallgraph.core.config import get_settings
from recallgraph.db.session import create_engine, create_session_factory
from recallgraph.evaluation.dataset import read_dataset
from recallgraph.evaluation.metrics import STRICT
from recallgraph.matching.engine import MatchQuery
from recallgraph.matching.service import match_product
from recallgraph.matching.text import content_terms


def is_dev(case_id: str) -> bool:
    return int(hashlib.sha256(case_id.encode()).hexdigest()[:8], 16) % 2 == 0


def q4(v: float) -> float:
    return round(v * 4) / 4


async def main(path: str) -> None:
    cases = [c for c in read_dataset(Path(path)) if c.kind == "product" and is_dev(c.case_id)]
    engine = create_engine(get_settings())
    factory = create_session_factory(engine)
    tp, fp, fp_per_case, tp_rank, terms_fp = Counter(), Counter(), Counter(), Counter(), Counter()
    examples = []
    async with factory() as s:
        for c in cases:
            expected = {tuple(e) for e in c.expected}
            out = await match_product(s, MatchQuery(**c.query), 20)
            n_terms = len(content_terms(c.query.get("description")))
            case_fp = 0
            for rank, r in enumerate(out.results, 1):
                if r.tier not in STRICT:
                    continue
                v = {x.name: x.value for x in r.signals}
                sig = f"{r.tier} mfr={v['manufacturer']} lex={q4(v['lexical'])} date={q4(v['date'])}"
                if (r.profile.source, r.profile.source_record_id) in expected:
                    tp[sig] += 1
                    tp_rank[rank] += 1
                else:
                    fp[sig] += 1
                    case_fp += 1
                    terms_fp[n_terms] += 1
                    if len(examples) < 8 and case_fp == 1:
                        examples.append({"query": c.query, "fp_title": r.profile.title, "signals": v})
            fp_per_case[min(case_fp, 10)] += 1
    await engine.dispose()
    print(json.dumps({
        "dev_product_cases": len(cases),
        "tp_signal_patterns": tp.most_common(8),
        "fp_signal_patterns": fp.most_common(8),
        "fp_count_per_case(10=10+)": sorted(fp_per_case.items()),
        "tp_rank_positions": sorted(tp_rank.items()),
        "fp_by_description_term_count": sorted(terms_fp.items()),
        "fp_examples": examples,
    }, indent=1, default=str))


asyncio.run(main(sys.argv[1]))
