"""FastAPI web server for the Golden Ticket Contest Enterprise AI Demo."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.agent import AgentConfigurationError, EnterpriseAIAgent
from app.data_layer import EnterpriseDataLayer, UnsafeSQLError
from app.docs_corpus import list_all_policy_docs

STATIC_DIR = Path(__file__).resolve().parent / "static"

data_layer = EnterpriseDataLayer()
agent = EnterpriseAIAgent(data_layer)

app = FastAPI(
    title="Enterprise AI with Data — Golden Ticket Demo",
    description="Python + Gemini Agentic Operations & Document Agent",
    version="1.0.0",
)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)


class SQLRequest(BaseModel):
    sql: str = Field(..., min_length=5, max_length=2000)


@app.get("/")
def serve_ui() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "data_backend": data_layer.backend,
        "ai_auth": agent.get_auth_status(),
    }


@app.get("/api/overview")
def overview() -> dict[str, Any]:
    return {
        "kpis": data_layer.get_kpi_overview(),
        "schema": data_layer.get_schema_summary(),
        "policy_docs": list_all_policy_docs(),
        "ai_auth": agent.get_auth_status(),
    }


@app.post("/api/sql")
def run_sql(req: SQLRequest) -> dict[str, Any]:
    try:
        return data_layer.execute_readonly_sql(req.sql)
    except UnsafeSQLError as exc:
        raise HTTPException(status_code=400, detail=f"Guardrail blocked query: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"SQL execution error: {exc}") from exc


@app.post("/api/ask")
def ask_agent(req: AskRequest) -> dict[str, Any]:
    try:
        return agent.ask(req.question)
    except AgentConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Gemini agent error: {exc}") from exc
