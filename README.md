# QueryForge | Explainable Natural-Language-to-SQL

**Status:** Fully runnable academic prototype, not a production LLM or a paper reproduction. All data is fictional.

QueryForge is an independently implemented, offline text-to-SQL engine designed to investigate whether **schema grounding, typed condition parsing, foreign-key-aware joins and parameterized execution** improve a transparent, template-based baseline.

**Research transparency:** See [RESEARCH.md](RESEARCH.md) for what the cited Seq2SQL paper actually implemented, how our baseline differs, and why the numbers cannot be directly compared.

![Python tests](https://img.shields.io/badge/tests-pytest-informational)

## Quick start

Requires Python 3.10+.

```bash
cd QueryForge
python -m queryforge seed
python -m queryforge ask "top 5 companies by revenue in 2024"
python -m queryforge ask "average revenue by sector in 2024"
python -m queryforge bench
python -m pytest -q                  # install pytest if needed
```

Optional interactive HTTP website (FastAPI):

```bash
python -m pip install -e ".[web]"
python -m uvicorn queryforge.app:app --reload
# Visit http://127.0.0.1:8000
```

A REST request:

```bash
curl -X POST http://127.0.0.1:8000/ask -H 'Content-Type: application/json' \
  -d '{"question":"companies with revenue above 100 million in 2024"}'
```

## System design

```
English question
   │
   ▼
Column phrase detection ── Database schema discovery (PRAGMA / foreign keys)
   │
   ▼
Semantic intent extraction
   ├── target column / count / sum / average
   ├── numeric comparisons and scale words (million, billion)
   ├── categorical filters and inferred country/sector
   ├── year constraints / top-N ordering
   └── grouping
   │
   ▼
Typed intent → join graph search → SQL AST-style string compilation
   │
   ▼
Parameterized SELECT query with read-only SQLite connection
   │
   ▼
Execution results, generated SQL, filter parameters, reasoning trace
```

The reference SQL in `data/benchmark.json` is **annotated separately** from the model predictions. The benchmark checks answer equivalence rather than merely comparing SQL strings.

### Implemented features

- SQLite schema introspection; foreign-key discovery and multi-table joins.
- Aggregates: `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`; `GROUP BY`; numerical `>`, `<`, `>=`, `<=`, `=`; categorical equality; top/bottom N.
- Schema-linked synonyms, including turnover/revenue, workforce/employees.
- Parameterized values, fully quoted schema-derived identifiers, read-only SQLite mode, maximum 100 output rows and a query time/step guard.
- Error responses for completely unsupported questions; basic explainability trace and content-aware, high-confidence correction of mistyped categorical values.
- CLI, REST API, zero-network demo dataset, automated tests, reproducible benchmark.

### What is *not* implemented

- No LLM, transformer, pretrained weights, backpropagation, reinforcement learning or self-correction loop. The generator is deterministic and rule-based.
- Not broad SQL or unrestricted natural-language understanding. Nested queries, OR logic, advanced joins, arithmetic, time-series growth, and linguistic ambiguity are **out of scope**.
- Value typo recovery relies on known schema content and does not repair arbitrary malformed SQL.
- SQL has a safe generation path but is *not certified secure* for sensitive production deployments.
- The natural-language linking rules have finance-domain aliases and do not generalize automatically to arbitrary databases.

## Measured evaluation

`data/finance.sqlite` contains **15 fictional businesses × 4 years = 60 financial observations**. The 71-question evaluation was authored for this prototype and covers named entities, categorical filters, aggregates, rankings, multi-table joins and inequalities. It is **not** a held-out public NLP benchmark and may overestimate generalization.

| Model | Correct / 71 | Execution accuracy |
|---|---:|---:|
| Template/keyword comparison (`baseline.py`) | 41 | 57.75% |
| QueryForge parser (`parser.py`) | 71 | 100.00% |

Results reproduced in `results/benchmark.json`, with per-question records. **These percentages must NOT be compared to Seq2SQL's original 35.9% or ColloQL's 90.7% because they use fundamentally different evaluation conditions.** This code does not reproduce either published neural model.

### How to make this into genuine research

1. Add support for WikiSQL's table and SQL JSON schema, using an isolated training/validation/test split.
2. Reproduce a published simple baseline with reported settings, or train a compact text-to-SQL transformer using an explicitly pinned checkpoint.
3. Build execution-aware candidate generation and correction with per-step failure analysis.
4. Evaluate on public held-out data, compare equal compute/memory budgets, and report bootstrap confidence intervals, exact match and execution accuracy.
5. Test out-of-domain adversarial paraphrases and multi-schema database generalization.

## Research context and attribution

The **idea** of mapping natural language to SQL is established research. This is a clean, independent implementation of a restricted algorithmic prototype, not adapted research source code.

- Zhong, Xiong & Socher, *Seq2SQL: Generating Structured Queries from Natural Language using Reinforcement Learning*, arXiv:1709.00103 (2017), https://arxiv.org/abs/1709.00103 . They reported a 35.9% seq2seq baseline and 59.4% Seq2SQL execution accuracy on WikiSQL.
- Radhakrishnan, Srikantan & Lin, *ColloQL: Robust Text-to-SQL Over Search Queries*, 2020, https://aclanthology.org/2020.intexsempar-1.5/ . They reported 90.7% WikiSQL execution accuracy with a BERT-based system.

**Originality:** All project source files here were newly written for this prototype; no code from either published implementation was copied. The research papers are credited for context and concepts. As with any code, independent authorship is not an absolute plagiarism-certification from a third-party similarity database.

## Repository map

- `queryforge/schema.py`: introspection, safe identifier quoting, join paths.
- `queryforge/parser.py`: grounded intent extraction.
- `queryforge/engine.py`: compiled SQL and read-only execution.
- `queryforge/baseline.py`: simpler comparison model.
- `queryforge/demo.py`: deterministic fictional company database generation.
- `queryforge/benchmark.py`: execution-equivalence evaluation.
- `queryforge/app.py`: browser application and HTTP API.
- `tests/`: correctness, API, security regression and benchmark tests.
- `data/benchmark.json`: readable test labels and gold SQL.
- `data/paraphrase_challenge.json`: separately authored set of 20 alternate wordings.
- `results/paraphrase_challenge.json`: additional evaluation of those 20 wordings (20/20 on the domain-specific set).
- `results/benchmark.json`: saved actual run, including per-case outcomes.

## Fair CV wording

> Built an independently implemented text-to-SQL engine with schema-aware joins, typed natural-language parsing and parameterized SQLite execution; achieved 71/71 correct answers on a 71-question, fictional finance-domain evaluation versus 41/71 for a basic template baseline.

Do **not** say that you improved a published neural model from 35.9% to 100%; this project did not do that.
