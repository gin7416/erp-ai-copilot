"""REST API: guarded SQL, Text-to-SQL, SOP search and grounded SOP answers.

    uvicorn erp_copilot.api:app --port 8000      # docs at http://127.0.0.1:8000/docs
"""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated

import duckdb
from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .copilot import Copilot, LLMNotConfigured
from .sql_guard import SqlGuardError


class SqlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sql: str = Field(min_length=1, max_length=5000)


class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=2, max_length=500)


@lru_cache(maxsize=1)
def get_copilot() -> Copilot:
    return Copilot()


CopilotDep = Annotated[Copilot, Depends(get_copilot)]

app = FastAPI(
    title="ERP AI Copilot",
    description="Text-to-SQL over dbt marts and RAG over SOP documents, backed by a local LLM. Demo data is synthetic.",
    version="0.1.0",
)


@app.get("/health")
def health(copilot: CopilotDep) -> dict:
    return {"status": "ok", "llm": copilot.chat.name if copilot.chat else None,
            "warehouse_ready": copilot.warehouse.path.exists(), "retrieval": copilot.retrieval_mode}


@app.get("/tables")
def tables(copilot: CopilotDep) -> list[dict]:
    return copilot.tables()


@app.post("/sql")
def run_sql(req: SqlRequest, copilot: CopilotDep) -> dict:
    try:
        return copilot.warehouse.run(req.sql).to_dict(max_rows=200)
    except SqlGuardError as exc:
        raise HTTPException(status_code=400, detail=f"SQL rejected: {exc}") from exc
    except duckdb.Error as exc:
        raise HTTPException(status_code=400, detail=f"SQL error: {str(exc).splitlines()[0]}") from exc


@app.post("/ask/data")
def ask_data(req: QuestionRequest, copilot: CopilotDep) -> dict:
    try:
        return copilot.text_to_sql.ask(req.question).to_dict()
    except LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/search/sop")
def search_sop(copilot: CopilotDep, q: Annotated[str, Query(min_length=2, max_length=300)],
               k: Annotated[int, Query(ge=1, le=10)] = 3) -> dict:
    return {"query": q, "mode": copilot.retrieval_mode, "hits": copilot.search_sop(q, k)}


@app.post("/ask/sop")
def ask_sop(req: QuestionRequest, copilot: CopilotDep) -> dict:
    try:
        return copilot.sop_qa.ask(req.question)
    except LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
