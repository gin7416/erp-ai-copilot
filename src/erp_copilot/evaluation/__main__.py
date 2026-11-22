"""Evaluation CLI.

    python -m erp_copilot.evaluation retrieval --modes bm25 dense hybrid
    python -m erp_copilot.evaluation sql --provider ollama --model qwen2.5-coder:3b
    python -m erp_copilot.evaluation sql --provider oracle          # harness self-check (expects 100%)
    python -m erp_copilot.evaluation report                         # results/*.json -> results/EVAL_REPORT.md
"""
from __future__ import annotations

import argparse
import json
import sys

from ..llm import OllamaEmbedder, make_chat
from ..rag import SopIndex
from ..settings import get_settings
from . import (RESULTS_DIR, SQL_CONFIGS, evaluate_retrieval, evaluate_sql, oracle_factory, run_metadata,
               write_json)


def _retrieval(args) -> int:
    s = get_settings()
    embedder = OllamaEmbedder(args.embed_model, s.llm_base_url) if {"dense", "hybrid"} & set(args.modes) else None
    index = SopIndex.from_directory(s.sop_dir)
    if embedder:
        index.add_embeddings(embedder)
    result = evaluate_retrieval(index, args.modes, embedder)
    result["meta"] = run_metadata({"embed_model": embedder.name if embedder else None, "chunks": len(index.chunks)})
    for mode, m in result["modes"].items():
        print(f"{mode:7s} hit@1={m['hit@1']:.3f} hit@3={m['hit@3']:.3f} mrr={m['mrr']:.3f} "
              f"paraphrase_hit@3={m['paraphrase_hit@3']:.3f}")
    if not args.no_write:
        print("written:", write_json("eval_retrieval.json", result))
    worst = min(m["hit@3"] for m in result["modes"].values())
    if args.min_hit_at_3 is not None and worst < args.min_hit_at_3:
        print(f"FAIL: hit@3 {worst} < threshold {args.min_hit_at_3}", file=sys.stderr)
        return 1
    return 0


def _sql(args) -> int:
    s = get_settings()
    if args.provider == "oracle":
        factory = oracle_factory
    else:
        factory = lambda _cfg, _golden: make_chat(args.provider, args.model, args.base_url or s.llm_base_url)  # noqa: E731
    result = evaluate_sql(s, factory, args.configs)
    result["meta"] = run_metadata({"provider": args.provider, "model": args.model if args.provider != "oracle" else "oracle"})
    for name, cfg in result["configs"].items():
        sm = cfg["summary"]
        print(f"{name:15s} exec={sm['executable_rate']:.3f} acc={sm['lenient_acc']:.3f} strict={sm['strict_acc']:.3f} "
              f"first_try={sm['first_attempt_acc']:.3f} fixed_by_retry={sm['fixed_by_retry']} "
              f"p50={sm['latency_p50_s']}s p95={sm['latency_p95_s']}s")
    if not args.no_write:
        print("written:", write_json(f"eval_sql_{args.provider}.json", result))
    if args.min_accuracy is not None:
        worst = min(c["summary"]["lenient_acc"] for c in result["configs"].values())
        if worst < args.min_accuracy:
            print(f"FAIL: accuracy {worst} < {args.min_accuracy}", file=sys.stderr)
            return 1
    return 0


def _report(_args) -> int:
    from .report import render

    path = RESULTS_DIR / "EVAL_REPORT.md"
    path.write_text(render(), encoding="utf-8")
    print("written:", path)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("retrieval")
    r.add_argument("--modes", nargs="+", default=["bm25"], choices=["bm25", "dense", "hybrid"])
    r.add_argument("--embed-model", default="bge-m3")
    r.add_argument("--min-hit-at-3", type=float)
    r.add_argument("--no-write", action="store_true")
    q = sub.add_parser("sql")
    q.add_argument("--provider", default="ollama", choices=["ollama", "openai", "oracle"])
    q.add_argument("--model", default="qwen2.5-coder:3b")
    q.add_argument("--base-url")
    q.add_argument("--configs", nargs="+", default=list(SQL_CONFIGS), choices=list(SQL_CONFIGS))
    q.add_argument("--min-accuracy", type=float)
    q.add_argument("--no-write", action="store_true")
    sub.add_parser("report")
    args = p.parse_args()
    return {"retrieval": _retrieval, "sql": _sql, "report": _report}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
