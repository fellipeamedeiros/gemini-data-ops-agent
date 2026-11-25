"""Automated verification suite for the Golden Ticket Enterprise AI Demo."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agent import compute_recovery_plan
from app.data_layer import EnterpriseDataLayer, UnsafeSQLError, validate_readonly_sql
from app.docs_corpus import search_policy_docs
from app.main import app


@pytest.mark.parametrize(
    "bad_sql",
    [
        "",
        "DROP TABLE payer_claims;",
        "DELETE FROM clinics WHERE clinic_id = 'CLN-SP01'",
        "UPDATE clinics SET daily_capacity = 999",
        "INSERT INTO clinics VALUES ('X','Y','Z','R',1,1,'M')",
        "SELECT * FROM clinics; DROP TABLE clinics;",
        "PRAGMA table_info(clinics)",
        "ATTACH DATABASE '/tmp/pwn.db' AS pwn",
    ],
)
def test_readonly_sql_guardrail_blocks_unsafe_queries(bad_sql: str) -> None:
    with pytest.raises(UnsafeSQLError):
        validate_readonly_sql(bad_sql)


def test_readonly_sql_guardrail_allows_select_and_with() -> None:
    q1 = validate_readonly_sql("SELECT * FROM clinics;")
    assert q1.endswith("LIMIT 100")

    q2 = validate_readonly_sql("WITH top_c AS (SELECT * FROM clinics LIMIT 2) SELECT * FROM top_c")
    assert q2.startswith("WITH top_c")


def test_database_seeding_and_kpis(tmp_path: Path) -> None:
    db = EnterpriseDataLayer(backend="sqlite", db_path=tmp_path / "test_ops.db")
    kpis = db.get_kpi_overview()
    assert kpis["total_90d_revenue_usd"] > 0
    assert kpis["denied_claims_usd"] > 0
    assert kpis["equipment_sla_alerts"] >= 2

    res = db.execute_readonly_sql(
        "SELECT payer_name, COUNT(*) AS cnt FROM payer_claims WHERE status = 'DENIED' GROUP BY payer_name ORDER BY cnt DESC"
    )
    assert res["row_count"] >= 1
    assert res["rows"][0]["payer_name"] == "VidaPlus Saude"


def test_policy_doc_search_grounds_root_causes() -> None:
    payer_docs = search_policy_docs("VidaPlus pre-auth denial MRI")
    assert payer_docs["match_count"] >= 1
    assert payer_docs["documents"][0]["doc_id"] == "DOC-001"

    sla_docs = search_policy_docs("MedTech equipment uptime SLA penalty Campinas")
    assert sla_docs["match_count"] >= 1
    assert sla_docs["documents"][0]["doc_id"] == "DOC-002"


def test_recovery_plan_calculator() -> None:
    plan = compute_recovery_plan(
        revenue_at_risk_usd=50000.0,
        recoverable_pct=78.0,
        implementation_cost_usd=8500.0,
        action_summary="Appeal denied claims and automate TISS pre-auth.",
    )
    assert plan["expected_recovery_usd"] == 39000.0
    assert plan["net_impact_usd"] == 30500.0
    assert plan["roi_multiple"] == 4.59


def test_fastapi_endpoints_and_negative_security() -> None:
    client = TestClient(app)

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    overview = client.get("/api/overview")
    assert overview.status_code == 200
    body = overview.json()
    assert len(body["schema"]) == 4
    assert len(body["policy_docs"]) == 4

    blocked = client.post("/api/sql", json={"sql": "DROP TABLE payer_claims;"})
    assert blocked.status_code == 400
    assert "Guardrail blocked query" in blocked.json()["detail"]

    ok_sql = client.post("/api/sql", json={"sql": "SELECT COUNT(*) AS n FROM clinics"})
    assert ok_sql.status_code == 200
    assert ok_sql.json()["rows"][0]["n"] == 5
