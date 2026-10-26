# Research context and reproducibility

**The original research is not reproduced or directly beaten by this repository.**

**Inspiration:** Zhong, Xiong & Socher (2017), [Seq2SQL: Generating Structured Queries from Natural Language using Reinforcement Learning](https://arxiv.org/abs/1709.00103). That paper introduced structured text-to-SQL model training for WikiSQL, reporting 59.4% execution accuracy against a 35.9% sequence-to-sequence baseline.

**What this project implements:** A domain-restricted, deterministic parser with SQLite schema introspection, graph-based foreign-key join discovery, parameterized query compilation, fuzzy categorical value matching, a browser API, and an intentionally weak keyword baseline. There is no transformer, trained NLP model, reinforcement learning, or execution-guided learning.

## Reproduce the numbers

```bash
python -m pip install -e '.[dev,web]'
python -m pytest -q
python -m queryforge bench
```

Evaluation uses 71 curated queries over 15 fictional companies and 60 annual observations, and scores execution-result equivalence against gold SQL. Results: 41/71 (57.75%) for the independent keyword baseline; 71/71 (100%) for the deterministic parser. An additional 20 **locally authored** paraphrases are included. This is not a public held-out benchmark and may be overfit to the parser vocabulary.

## Research roadmap

- Support WikiSQL or Spider/BIRD inputs with disjoint train/development/test splits.
- Implement a neural baseline under pinned versions and controlled compute.
- Add candidate ranking and validated execution-aware corrections.
- Report public-dataset execution accuracy, latency, failure categories and confidence intervals.
