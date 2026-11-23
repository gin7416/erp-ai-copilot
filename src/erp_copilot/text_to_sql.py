"""Natural-language question -> guarded DuckDB SQL -> result, with an error-feedback correction loop."""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

import duckdb

from .llm import ChatModel, Message
from .sql_guard import SqlGuardError
from .warehouse import QueryResult

SYSTEM_PROMPT = """你是企業資料分析助理，負責把使用者的中文問題轉成 DuckDB SQL。
規則：
1. 只能使用下方 schema 列出的 marts 資料表，表名一律寫成 marts.<table>。
2. 只輸出一個 SELECT 查詢，放在 ```sql 程式碼區塊中，不要任何解釋。
3. 遵守欄位說明裡的商業規則（例如計算營收要排除已取消訂單、最新庫存只取最新快照）。
4. 不要自行假設資料表或欄位；字串值請使用欄位說明中出現的實際值。

資料庫 schema：
{schema}"""

FEW_SHOT: list[tuple[str, str]] = [
    ("每個倉庫在 2026-03-31 的總庫存量是多少？",
     "SELECT w.warehouse_name, SUM(i.on_hand_qty) AS total_qty\n"
     "FROM marts.fct_inventory i JOIN marts.dim_warehouses w USING (warehouse_id)\n"
     "WHERE i.snapshot_date = DATE '2026-03-31'\nGROUP BY w.warehouse_name ORDER BY total_qty DESC"),
    ("2025 年 OEM 客戶貢獻多少營收？",
     "SELECT SUM(s.revenue) AS revenue\nFROM marts.fct_sales s JOIN marts.dim_customers c USING (customer_id)\n"
     "WHERE c.segment = 'OEM' AND s.status <> 'cancelled'\n  AND s.order_date >= DATE '2025-01-01' AND s.order_date < DATE '2026-01-01'"),
]

RETRY_PROMPT = "上一個 SQL 無法執行，錯誤訊息：{error}\n請修正後重新輸出一個 SELECT 查詢（只要 ```sql 程式碼區塊）。"

_FENCE = re.compile(r"```(?:sql|SQL)?\s*(.*?)```", re.S)
_STATEMENT_START = re.compile(
    r"^\s*(with|select|insert|update|delete|drop|create|alter|attach|copy|pragma)\b", re.I | re.M)


def extract_sql(text: str) -> str:
    """Take the first fenced block if present, otherwise the text from the first SELECT/WITH."""
    m = _FENCE.search(text)
    if m:
        return m.group(1).strip().rstrip(";").strip()
    # any statement at the start of a line (so a bare DELETE reaches the guard and is reported as such)
    m = _STATEMENT_START.search(text) or re.search(r"\b(with|select)\b", text, re.I)
    return text[m.start():].strip().rstrip(";").strip() if m else ""


@dataclass
class Attempt:
    raw_output: str
    sql: str
    error_type: str | None = None   # None | "no_sql" | "guard" | "execution"
    error: str | None = None


@dataclass
class SqlAnswer:
    question: str
    ok: bool
    sql: str | None
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    attempts: list[Attempt] = field(default_factory=list)
    latency_s: float = 0.0
    model: str = ""

    def to_dict(self, max_rows: int = 50) -> dict[str, Any]:
        d = asdict(self)
        d["rows"] = QueryResult(self.sql or "", self.columns, self.rows).to_dict(max_rows)["rows"]
        d["row_count"] = len(self.rows)
        return d


class SqlExecutor(Protocol):
    """Anything that validates and runs SQL: the DuckDB Warehouse, or a benchmark's SQLite database."""

    def run(self, sql: str, max_rows: int = 200) -> QueryResult: ...


class TextToSQL:
    def __init__(self, chat: ChatModel, warehouse: SqlExecutor, schema: str, max_attempts: int = 2,
                 few_shot: bool = True, max_rows: int = 200, system_prompt: str = SYSTEM_PROMPT,
                 examples: list[tuple[str, str]] | None = None, retry_prompt: str = RETRY_PROMPT,
                 execution_errors: tuple[type[Exception], ...] = (duckdb.Error,)):
        self.chat, self.warehouse = chat, warehouse
        self.system = system_prompt.format(schema=schema)
        self.max_attempts, self.max_rows = max_attempts, max_rows
        self.examples = (FEW_SHOT if examples is None else examples) if few_shot else []
        self.retry_prompt, self.execution_errors = retry_prompt, execution_errors

    def _messages(self, question: str) -> list[Message]:
        msgs: list[Message] = [{"role": "system", "content": self.system}]
        for q, sql in self.examples:
            msgs += [{"role": "user", "content": q}, {"role": "assistant", "content": f"```sql\n{sql}\n```"}]
        msgs.append({"role": "user", "content": question})
        return msgs

    def ask(self, question: str) -> SqlAnswer:
        started = time.perf_counter()
        messages = self._messages(question)
        answer = SqlAnswer(question=question, ok=False, sql=None, model=self.chat.name)
        for _ in range(self.max_attempts):
            raw = self.chat.chat(messages)
            sql = extract_sql(raw)
            attempt = Attempt(raw_output=raw, sql=sql)
            answer.attempts.append(attempt)
            if not sql:
                attempt.error_type, attempt.error = "no_sql", "回覆中沒有 SQL"
            else:
                try:
                    result = self.warehouse.run(sql, max_rows=self.max_rows)
                except SqlGuardError as exc:
                    attempt.error_type, attempt.error = "guard", str(exc)
                except self.execution_errors as exc:
                    attempt.error_type, attempt.error = "execution", (str(exc).splitlines() or [""])[0][:300]
                else:
                    answer.ok, answer.sql = True, result.sql
                    answer.columns, answer.rows = result.columns, result.rows
                    break
            messages = messages + [{"role": "assistant", "content": raw},
                                   {"role": "user", "content": self.retry_prompt.format(error=attempt.error)}]
        if not answer.ok and answer.attempts:
            answer.sql = answer.attempts[-1].sql or None
        answer.latency_s = round(time.perf_counter() - started, 3)
        return answer
