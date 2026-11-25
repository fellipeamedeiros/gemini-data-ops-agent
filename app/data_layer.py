"""Dual-backend enterprise data layer (SQLite default + optional BigQuery).

Enforces strict read-only SQL guardrails so an AI agent can safely query
structured operational data without any risk of destructive DML/DDL execution.
"""

from __future__ import annotations

import os
import random
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "enterprise_ops.db"

FORBIDDEN_SQL_PATTERN = re.compile(
    r"\b("
    r"INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|"
    r"ATTACH|DETACH|PRAGMA|VACUUM|GRANT|REVOKE|MERGE|EXEC|EXECUTE|CALL"
    r")\b",
    re.IGNORECASE,
)


class UnsafeSQLError(ValueError):
    """Raised when a SQL query violates the read-only guardrail."""


def validate_readonly_sql(sql: str, max_rows: int = 100) -> str:
    """Validate that a SQL query is strictly a single read-only SELECT/WITH statement."""
    if not sql or not sql.strip():
        raise UnsafeSQLError("SQL query cannot be empty.")

    # Strip SQL line and block comments before inspection.
    cleaned = re.sub(r"--[^\n]*", "", sql)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL).strip()
    cleaned = cleaned.rstrip(";").strip()

    if not cleaned:
        raise UnsafeSQLError("SQL query is empty after stripping comments.")

    if ";" in cleaned:
        raise UnsafeSQLError(
            "Multiple SQL statements are blocked by the read-only guardrail."
        )

    upper_start = cleaned.lstrip("(").upper()
    if not (upper_start.startswith("SELECT") or upper_start.startswith("WITH")):
        raise UnsafeSQLError(
            "Only read-only SELECT or WITH queries are permitted."
        )

    match = FORBIDDEN_SQL_PATTERN.search(cleaned)
    if match:
        raise UnsafeSQLError(
            f"Blocked forbidden SQL keyword '{match.group(1).upper()}' "
            "under read-only governance policy."
        )

    if not re.search(r"\bLIMIT\s+\d+\b", cleaned, re.IGNORECASE):
        cleaned = f"{cleaned} LIMIT {max_rows}"

    return cleaned


def init_sqlite_database(db_path: Path | None = None, force_reseed: bool = False) -> Path:
    """Create and seed a realistic, 100% synthetic diagnostic-clinic operations DB."""
    target = Path(db_path or os.getenv("SQLITE_DB_PATH") or DEFAULT_DB_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists() and not force_reseed:
        return target

    if target.exists():
        target.unlink()

    conn = sqlite3.connect(target)
    try:
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE clinics (
                clinic_id TEXT PRIMARY KEY,
                clinic_name TEXT NOT NULL,
                city TEXT NOT NULL,
                region TEXT NOT NULL,
                daily_capacity INTEGER NOT NULL,
                monthly_revenue_target_usd REAL NOT NULL,
                ops_manager TEXT NOT NULL
            );

            CREATE TABLE exam_volume_daily (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_date TEXT NOT NULL,
                clinic_id TEXT NOT NULL,
                modality TEXT NOT NULL,
                exams_completed INTEGER NOT NULL,
                avg_turnaround_hours REAL NOT NULL,
                sla_breach_count INTEGER NOT NULL,
                gross_revenue_usd REAL NOT NULL,
                FOREIGN KEY (clinic_id) REFERENCES clinics(clinic_id)
            );

            CREATE TABLE payer_claims (
                claim_id TEXT PRIMARY KEY,
                claim_date TEXT NOT NULL,
                clinic_id TEXT NOT NULL,
                payer_name TEXT NOT NULL,
                modality TEXT NOT NULL,
                billed_usd REAL NOT NULL,
                approved_usd REAL NOT NULL,
                status TEXT NOT NULL,
                denial_reason TEXT NOT NULL,
                days_to_pay INTEGER NOT NULL,
                FOREIGN KEY (clinic_id) REFERENCES clinics(clinic_id)
            );

            CREATE TABLE equipment_telemetry (
                telemetry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_month TEXT NOT NULL,
                clinic_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                modality TEXT NOT NULL,
                vendor_name TEXT NOT NULL,
                uptime_pct REAL NOT NULL,
                unscheduled_downtime_hours REAL NOT NULL,
                maintenance_cost_usd REAL NOT NULL,
                alert_status TEXT NOT NULL,
                FOREIGN KEY (clinic_id) REFERENCES clinics(clinic_id)
            );
            """
        )

        clinics = [
            ("CLN-SP01", "Paulista Flagship Diagnostics", "Sao Paulo", "SP-Metro", 180, 620000.0, "Ana Ribeiro"),
            ("CLN-SP02", "Morumbi Advanced Imaging", "Sao Paulo", "SP-Metro", 150, 510000.0, "Carlos Mendes"),
            ("CLN-CPS1", "Campinas Regional Hub", "Campinas", "SP-Interior", 130, 420000.0, "Juliana Costa"),
            ("CLN-RJ01", "Barra Precision Clinic", "Rio de Janeiro", "RJ-Metro", 140, 470000.0, "Rafael Oliveira"),
            ("CLN-BH01", "Savassi Diagnostic Center", "Belo Horizonte", "MG-Metro", 120, 380000.0, "Fernanda Lima"),
        ]
        cur.executemany(
            "INSERT INTO clinics VALUES (?, ?, ?, ?, ?, ?, ?)", clinics
        )

        rng = random.Random(20261125)
        start_day = date(2026, 8, 25)
        modalities = [
            ("MRI", 540.0, 26, 18.0),
            ("CT_SCAN", 320.0, 34, 10.5),
            ("PET_CT", 980.0, 10, 22.0),
            ("ULTRASOUND", 115.0, 55, 4.5),
        ]

        exam_rows = []
        for day_offset in range(90):
            current_day = start_day + timedelta(days=day_offset)
            iso_day = current_day.isoformat()
            is_recent_q4 = current_day >= date(2026, 10, 1)

            for clinic_id, _, _, _, capacity, _, _ in clinics:
                scale = capacity / 150.0
                for modality, unit_price, base_vol, base_tat in modalities:
                    vol = max(4, int(base_vol * scale * rng.uniform(0.84, 1.18)))
                    tat = round(base_tat * rng.uniform(0.85, 1.15), 1)
                    breaches = 0

                    # Inject realistic operational story #1:
                    # Campinas MRI scanner degradation in Oct/Nov causes SLA breaches & lost volume.
                    if clinic_id == "CLN-CPS1" and modality == "MRI" and is_recent_q4:
                        vol = max(6, int(vol * 0.62))
                        tat = round(tat * 1.85, 1)
                        breaches = rng.randint(4, 11)

                    # Inject operational story #2:
                    # Paulista Flagship running above 92% utilization on CT/MRI -> overflow opportunity to Morumbi.
                    if clinic_id == "CLN-SP01" and modality in ("MRI", "CT_SCAN"):
                        vol = int(vol * 1.16)
                        if tat > 20.0:
                            breaches = rng.randint(2, 6)

                    revenue = round(vol * unit_price, 2)
                    exam_rows.append(
                        (iso_day, clinic_id, modality, vol, tat, breaches, revenue)
                    )

        cur.executemany(
            """
            INSERT INTO exam_volume_daily
            (exam_date, clinic_id, modality, exams_completed, avg_turnaround_hours, sla_breach_count, gross_revenue_usd)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            exam_rows,
        )

        # Seed 600 synthetic payer claims with a clear Q3/Q4 denial spike on VidaPlus Saude.
        payers = [
            "VidaPlus Saude",
            "SulMed Corporativo",
            "BrasilCare Planos",
            "NovaSaude Empresarial",
        ]
        claim_rows = []
        for idx in range(1, 601):
            claim_day = start_day + timedelta(days=rng.randint(0, 89))
            clinic_id = rng.choice(clinics)[0]
            payer = rng.choice(payers)
            modality, unit_price, _, _ = rng.choice(modalities)
            billed = round(unit_price * rng.uniform(0.95, 1.25), 2)

            # Story #3: VidaPlus Saude tightened digital pre-auth rules for MRI & PET_CT > $450 in Q3/Q4.
            if (
                payer == "VidaPlus Saude"
                and modality in ("MRI", "PET_CT")
                and billed > 450.0
                and rng.random() < 0.42
            ):
                status = "DENIED"
                reason = "MISSING_PRE_AUTH"
                approved = 0.0
                days_to_pay = rng.randint(45, 72)
            elif rng.random() < 0.06:
                status = "DENIED"
                reason = rng.choice(["DUPLICATE_CODE", "EXPIRED_PROTOCOL"])
                approved = 0.0
                days_to_pay = rng.randint(35, 60)
            else:
                status = "APPROVED"
                reason = "NONE"
                approved = round(billed * rng.uniform(0.94, 1.0), 2)
                days_to_pay = rng.randint(18, 34)

            claim_rows.append(
                (
                    f"CLM-2026-{idx:05d}",
                    claim_day.isoformat(),
                    clinic_id,
                    payer,
                    modality,
                    billed,
                    approved,
                    status,
                    reason,
                    days_to_pay,
                )
            )

        cur.executemany(
            "INSERT INTO payer_claims VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            claim_rows,
        )

        # Equipment telemetry for Sep, Oct, Nov 2026 — highlighting Campinas MRI-02 SLA violation.
        telemetry_rows = [
            ("2026-09", "CLN-SP01", "MRI-SP01-A", "MRI", "MedTech Diagnostics", 98.4, 2.5, 18500.0, "HEALTHY"),
            ("2026-10", "CLN-SP01", "MRI-SP01-A", "MRI", "MedTech Diagnostics", 97.9, 3.2, 18500.0, "HEALTHY"),
            ("2026-11", "CLN-SP01", "MRI-SP01-A", "MRI", "MedTech Diagnostics", 98.1, 2.8, 18500.0, "HEALTHY"),
            ("2026-09", "CLN-SP02", "MRI-SP02-A", "MRI", "MedTech Diagnostics", 99.1, 1.0, 17800.0, "HEALTHY"),
            ("2026-10", "CLN-SP02", "MRI-SP02-A", "MRI", "MedTech Diagnostics", 98.8, 1.5, 17800.0, "HEALTHY"),
            ("2026-11", "CLN-SP02", "MRI-SP02-A", "MRI", "MedTech Diagnostics", 99.0, 1.2, 17800.0, "HEALTHY"),
            ("2026-09", "CLN-CPS1", "MRI-CPS1-02", "MRI", "MedTech Diagnostics", 96.5, 6.0, 18000.0, "WATCH"),
            ("2026-10", "CLN-CPS1", "MRI-CPS1-02", "MRI", "MedTech Diagnostics", 88.2, 24.5, 24200.0, "SLA_BREACH"),
            ("2026-11", "CLN-CPS1", "MRI-CPS1-02", "MRI", "MedTech Diagnostics", 85.4, 31.0, 26800.0, "SLA_BREACH"),
            ("2026-10", "CLN-RJ01", "PET-RJ01-01", "PET_CT", "MedTech Diagnostics", 97.2, 4.5, 22000.0, "HEALTHY"),
            ("2026-11", "CLN-RJ01", "PET-RJ01-01", "PET_CT", "MedTech Diagnostics", 96.8, 5.1, 22000.0, "HEALTHY"),
            ("2026-11", "CLN-BH01", "CT-BH01-01", "CT_SCAN", "MedTech Diagnostics", 98.5, 2.0, 14500.0, "HEALTHY"),
        ]
        cur.executemany(
            """
            INSERT INTO equipment_telemetry
            (report_month, clinic_id, device_id, modality, vendor_name, uptime_pct, unscheduled_downtime_hours, maintenance_cost_usd, alert_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            telemetry_rows,
        )

        conn.commit()
    finally:
        conn.close()

    return target


class EnterpriseDataLayer:
    """Executes validated read-only SQL against SQLite (default) or BigQuery."""

    def __init__(self, backend: str | None = None, db_path: Path | None = None) -> None:
        self.backend = (backend or os.getenv("DATA_BACKEND", "sqlite")).lower()
        self.db_path = init_sqlite_database(db_path) if self.backend == "sqlite" else None
        self.bq_project = os.getenv("GOOGLE_CLOUD_PROJECT")

    def execute_readonly_sql(self, sql: str, max_rows: int = 100) -> dict[str, Any]:
        """Validate and execute a read-only SQL query on the configured backend."""
        safe_sql = validate_readonly_sql(sql, max_rows=max_rows)

        if self.backend == "bigquery":
            return self._execute_bigquery(safe_sql)
        return self._execute_sqlite(safe_sql)

    def _execute_sqlite(self, safe_sql: str) -> dict[str, Any]:
        assert self.db_path is not None
        # Open SQLite in read-only URI mode as defense-in-depth.
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(safe_sql)
            rows = [dict(row) for row in cur.fetchall()]
            columns = [desc[0] for desc in cur.description] if cur.description else []
            return {
                "backend": "sqlite",
                "executed_sql": safe_sql,
                "columns": columns,
                "row_count": len(rows),
                "rows": rows,
            }
        finally:
            conn.close()

    def _execute_bigquery(self, safe_sql: str) -> dict[str, Any]:
        from google.cloud import bigquery  # Imported lazily for portability.

        client = bigquery.Client(project=self.bq_project)
        job_config = bigquery.QueryJobConfig(
            maximum_bytes_billed=100 * 1024 * 1024  # 100 MB cost guardrail.
        )
        job = client.query(safe_sql, job_config=job_config)
        result = job.result()
        rows = [dict(row.items()) for row in result]
        columns = [field.name for field in result.schema]
        return {
            "backend": "bigquery",
            "executed_sql": safe_sql,
            "columns": columns,
            "row_count": len(rows),
            "rows": rows,
            "bytes_processed": job.total_bytes_processed,
        }

    def get_schema_summary(self) -> list[dict[str, Any]]:
        """Return structured table/column metadata for grounding the Gemini agent."""
        if self.backend != "sqlite":
            return [
                {
                    "table": "BigQuery Dataset",
                    "note": "Set BIGQUERY_DATASET or query fully-qualified `project.dataset.table`.",
                }
            ]

        assert self.db_path is not None
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        try:
            tables = [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                ).fetchall()
            ]
            summary = []
            for table in tables:
                cols = [
                    {"name": c[1], "type": c[2]}
                    for c in conn.execute(f"PRAGMA table_info({table})").fetchall()
                ]
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                summary.append({"table": table, "row_count": count, "columns": cols})
            return summary
        finally:
            conn.close()

    def get_kpi_overview(self) -> dict[str, Any]:
        """Compute live executive KPIs directly from the active database."""
        rev = self.execute_readonly_sql(
            "SELECT ROUND(SUM(gross_revenue_usd), 2) AS total_rev, "
            "SUM(exams_completed) AS total_exams, "
            "SUM(sla_breach_count) AS total_breaches "
            "FROM exam_volume_daily"
        )["rows"][0]
        claims = self.execute_readonly_sql(
            "SELECT ROUND(SUM(CASE WHEN status = 'DENIED' THEN billed_usd ELSE 0 END), 2) AS denied_usd, "
            "COUNT(CASE WHEN status = 'DENIED' THEN 1 END) AS denied_count, "
            "COUNT(*) AS total_claims "
            "FROM payer_claims"
        )["rows"][0]
        alerts = self.execute_readonly_sql(
            "SELECT COUNT(*) AS sla_breach_devices "
            "FROM equipment_telemetry WHERE alert_status = 'SLA_BREACH'"
        )["rows"][0]

        return {
            "total_90d_revenue_usd": rev["total_rev"],
            "total_exams_completed": rev["total_exams"],
            "total_sla_breaches": rev["total_breaches"],
            "denied_claims_usd": claims["denied_usd"],
            "denied_claims_count": claims["denied_count"],
            "total_claims_count": claims["total_claims"],
            "equipment_sla_alerts": alerts["sla_breach_devices"],
        }
