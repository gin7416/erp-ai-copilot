"""Offline evaluation: Text-to-SQL execution accuracy (with ablations) and SOP retrieval quality."""
from __future__ import annotations

import json
import platform
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from ..llm import ChatModel, ScriptedChat
from ..rag import Embedder, SopIndex
from ..semantic import schema_context
from ..settings import PROJECT_ROOT, Settings
from ..text_to_sql import TextToSQL
from ..warehouse import Warehouse
from .compare import lenient_match, strict_match

EVAL_DIR = PROJECT_ROOT / "eval"
RESULTS_DIR = PROJECT_ROOT / "results"

# name -> (use dbt descriptions + few-shot examples, max attempts)
SQL_CONFIGS: dict[str, tuple[bool, int]] = {
    "schema_only": (False, 1),      # table/column names + types only
    "semantic_retry": (True, 2),    # + dbt business-rule descriptions + 2 examples + error-feedback retry
}


def load_golden(name: str) -> list[dict]:
    return yaml.safe_load((EVAL_DIR / name).read_text(encoding="utf-8"))


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def evaluate_sql(settings: Settings, chat_factory, configs: list[str], golden: list[dict] | None = None) -> dict:
    """Run each config over the golden set. `chat_factory(config, golden)` returns a ChatModel."""
    golden = golden or load_golden("golden_sql.yaml")
    wh = Warehouse(settings.duckdb_path)
    reference = {g["id"]: wh.run(g["sql"], max_rows=1000).rows for g in golden}
    out: dict[str, Any] = {"configs": {}}
    for name in configs:
        with_desc, attempts = SQL_CONFIGS[name]
        chat: ChatModel = chat_factory(name, golden)
        t2s = TextToSQL(chat, wh, schema_context(wh, settings.dbt_dir, with_descriptions=with_desc),
                        max_attempts=attempts, few_shot=with_desc, max_rows=1000)
        items = []
        for g in golden:
            ans = t2s.ask(g["question"])
            ref = reference[g["id"]]
            strict = ans.ok and strict_match(ans.rows, ref)
            lenient = ans.ok and lenient_match(ans.rows, ref)
            first = ans.attempts[0] if ans.attempts else None
            items.append({
                "id": g["id"], "level": g["level"], "question": g["question"], "sql": ans.sql,
                "executed": ans.ok, "strict": strict, "lenient": lenient,
                "attempts": len(ans.attempts),
                "correct_first_attempt": lenient and len(ans.attempts) == 1,
                "error_types": [a.error_type for a in ans.attempts if a.error_type],
                "last_error": next((a.error for a in reversed(ans.attempts) if a.error), None),
                "latency_s": ans.latency_s,
                "outcome": ("correct" if lenient else "wrong_result" if ans.ok else
                            (ans.attempts[-1].error_type if ans.attempts else "no_attempt")),
            })
        out["configs"][name] = {"model": chat.name, "with_descriptions": with_desc, "max_attempts": attempts,
                                "summary": summarize_sql(items), "items": items}
    return out


def summarize_sql(items: list[dict]) -> dict:
    n = len(items)
    lat = [i["latency_s"] for i in items]
    by_level: dict[str, dict] = {}
    for level in ("easy", "medium", "hard"):
        sub = [i for i in items if i["level"] == level]
        if sub:
            by_level[level] = {"n": len(sub), "lenient_acc": round(sum(i["lenient"] for i in sub) / len(sub), 3)}
    outcomes: dict[str, int] = {}
    for i in items:
        outcomes[i["outcome"]] = outcomes.get(i["outcome"], 0) + 1
    return {
        "n": n,
        "executable_rate": round(sum(i["executed"] for i in items) / n, 3),
        "strict_acc": round(sum(i["strict"] for i in items) / n, 3),
        "lenient_acc": round(sum(i["lenient"] for i in items) / n, 3),
        "first_attempt_acc": round(sum(i["correct_first_attempt"] for i in items) / n, 3),
        "fixed_by_retry": sum(1 for i in items if i["lenient"] and i["attempts"] > 1),
        "by_level": by_level,
        "outcomes": outcomes,
        "latency_p50_s": round(statistics.median(lat), 2) if lat else 0,
        "latency_p95_s": round(_pct(lat, 0.95), 2),
    }


def oracle_factory(_config: str, golden: list[dict]) -> ChatModel:
    """Answers every question with its reference SQL: checks the harness itself scores 100%."""
    return ScriptedChat([f"```sql\n{g['sql']}\n```" for g in golden], name="oracle")


def evaluate_retrieval(index: SopIndex, modes: list[str], embedder: Embedder | None = None,
                       golden: list[dict] | None = None) -> dict:
    golden = golden or load_golden("golden_sop.yaml")
    out: dict[str, Any] = {"n": len(golden), "modes": {}}
    for mode in modes:
        rows, rr = [], []
        for g in golden:
            hits = [h["chunk_id"].split("-")[0] for h in index.search(g["question"], k=5, mode=mode, embedder=embedder)]
            rank = hits.index(g["expected"]) + 1 if g["expected"] in hits else None
            rr.append(1 / rank if rank else 0.0)
            rows.append({"id": g["id"], "question": g["question"], "expected": g["expected"], "rank": rank,
                         "paraphrase": bool(g.get("paraphrase")), "top3": hits[:3]})

        def hit_at(k: int, subset: list[dict]) -> float:
            return round(sum(1 for r in subset if r["rank"] and r["rank"] <= k) / max(len(subset), 1), 3)

        para = [r for r in rows if r["paraphrase"]]
        out["modes"][mode] = {
            "hit@1": hit_at(1, rows), "hit@3": hit_at(3, rows), "mrr": round(sum(rr) / len(rr), 3),
            "paraphrase_hit@3": hit_at(3, para), "n_paraphrase": len(para), "items": rows,
        }
    return out


def run_metadata(extra: dict | None = None) -> dict:
    return {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "machine": f"{platform.system()} {platform.machine()}", "python": platform.python_version(),
            **(extra or {})}


def write_json(name: str, data: dict) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path
