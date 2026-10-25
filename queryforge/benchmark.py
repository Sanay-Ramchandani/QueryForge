"""Evaluate predicted SQL by answer equivalence to independently annotated SQL."""
import json
import sqlite3
from pathlib import Path
from .engine import QueryEngine, QueryError
from .baseline import keyword_baseline


def canonical(rows):
    """Execution-result equivalence, insensitive to row ordering except ranking."""
    return sorted(json.dumps(tuple(row),sort_keys=True,default=str) for row in rows)


def run_benchmark(database, jsonfile, save_path=None):
    cases=json.loads(Path(jsonfile).read_text())
    engine=QueryEngine(database)
    details=[]; upgraded=0; baseline=0
    with sqlite3.connect(database) as conn:
        for case in cases:
            expected=[tuple(r) for r in conn.execute(case['reference_sql'])]
            predicted_rows=None; error=None
            try:
                result=engine.ask(case['question'])
                predicted_rows=[tuple(r.values()) for r in result.rows]
            except QueryError as exc:
                error=str(exc)
            base_rows=keyword_baseline(database,case['question'])
            ordered=case.get('ordered',False)
            matches=(lambda x: x==expected if ordered else canonical(x)==canonical(expected))
            good=predicted_rows is not None and matches(predicted_rows)
            base_good=base_rows is not None and matches(base_rows)
            upgraded+=bool(good);baseline+=bool(base_good)
            details.append({'question':case['question'],'category':case.get('category','other'),
                            'correct':bool(good),'baseline_correct':bool(base_good),'error':error})
    summary={'dataset':'locally authored, fictional SQLite business Q/A set (NOT WikiSQL)',
             'sample_count':len(cases),'engine_correct':upgraded,'engine_accuracy':round(upgraded/len(cases),4),
             'baseline_correct':baseline,'baseline_accuracy':round(baseline/len(cases),4),
             'per_case':details}
    if save_path:
        Path(save_path).parent.mkdir(parents=True,exist_ok=True)
        Path(save_path).write_text(json.dumps(summary,indent=2))
    return summary
