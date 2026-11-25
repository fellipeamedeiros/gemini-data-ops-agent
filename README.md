# Enterprise AI with Data — Gemini Data & Ops Agent

A clean, readable **Python + FastAPI + Gemini (`google-genai` SDK)** reference demo showing how an enterprise AI agent unifies **governed SQL/BigQuery analytics** with **unstructured policy & SLA documents** using live Function Calling.

## The Enterprise Challenge

Commercial and mid-market enterprises (healthcare diagnostics, retail, logistics, manufacturing) operate across **two disconnected worlds**:

1. **Structured Operational & Financial Data** (BigQuery / SQL tables: exam volumes, claims denials, turnaround SLAs, equipment uptime).
2. **Unstructured Policy & Contract Documents** (payer reimbursement bulletins, vendor maintenance SLA penalty schedules, operational overflow playbooks, LGPD governance standards).

Traditional BI dashboards show *what* dropped, but cannot read contracts to explain *why* or quantify *how much can be recovered*. Pure chatbots read PDFs, but hallucinate numbers without governed SQL access.

## The Python Solution

In ~200 lines of idiomatic Python (`app/agent.py`), **Gemini Function Calling** bridges both worlds with enterprise-grade governance:

- **`run_readonly_sql`**: Strict read-only SQL guardrail (`SELECT`/`WITH` only; blocks `DROP`/`DELETE`/`UPDATE`/`INSERT`/`PRAGMA`/multi-statement SQL at both regex and read-only SQLite URI / BigQuery 100 MB `maximum_bytes_billed` layers).
- **`search_policy_docs`**: Grounded citation search across unstructured contracts and policy bulletins (`DOC-001`–`DOC-004`).
- **`compute_recovery_plan`**: Deterministic financial recovery & ROI calculator (zero LLM math hallucination).
- **Live Auditable Trajectory**: Every tool call, generated SQL statement, row count, policy citation, and millisecond latency is rendered side-by-side in the executive UI.

---

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/fellipeamedeiros/gemini-data-ops-agent.git
cd gemini-data-ops-agent
```

### 2. Run with Vertex AI (Recommended)

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project "<YOUR_GCP_PROJECT_ID>"

export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_PROJECT="<YOUR_GCP_PROJECT_ID>"
export GOOGLE_CLOUD_LOCATION="global"
bash run_demo.sh
```

Open `http://localhost:8080` in your browser.

### 3. Run with a Gemini API Key

```bash
export GOOGLE_GENAI_USE_VERTEXAI=false
export GEMINI_API_KEY="<YOUR_GEMINI_API_KEY>"
bash run_demo.sh
```

### 4. Switch from Local SQLite to Live BigQuery (1 Env Var)

```bash
export DATA_BACKEND=bigquery
export GOOGLE_CLOUD_PROJECT="<YOUR_GCP_PROJECT_ID>"
bash run_demo.sh
```

### 5. Run Automated Tests

```bash
.venv/bin/python -m pytest -v tests/test_demo.py
```

---

## 10-Minute Live Demo Flow

| Time | Segment | Live Action |
| :--- | :--- | :--- |
| **0:00–1:30** | **Hook & Business Problem** | Open the live KPI cards (**Denied Claims Revenue at Risk** & **Active Equipment SLA Alerts**) and frame the gap between structured BI tables and unstructured contracts. |
| **1:30–4:00** | **Demo Moment 1: Revenue Leakage + Policy Root Cause** | Click **Prompt #1**. Show the **Auditable Tool Trajectory** as Gemini writes SQL against `payer_claims`, finds `VidaPlus Saude` `MISSING_PRE_AUTH` denials, retrieves `DOC-001`, and computes exact net USD recovery & ROI. |
| **4:00–6:00** | **Demo Moment 2: Equipment SLA Penalty Claim** | Click **Prompt #2**. Show Gemini joining `equipment_telemetry` (`MRI-CPS1-02`) with `DOC-002` (MedTech 96% uptime / 15%–25% fee credit clause). |
| **6:00–7:30** | **Demo Moment 3: Live Negative Security Test** | Open the **SQL Guardrail Sandbox** and click **Attempt `DROP TABLE payer_claims;`**. Show the instant **HTTP 400 Guardrail Blocked** response (`DOC-004`). |
| **7:30–9:00** | **Python Code Walkthrough** | Walk through `app/agent.py` (3 tool declarations + function-calling loop) and `app/data_layer.py` (`DATA_BACKEND=bigquery` 1-flag switch). |
| **9:00–10:00** | **Wrap-Up** | Highlight how teams can point the same Python template at their own BigQuery tables and policy PDFs in minutes. |

> **Data Disclaimer**: All clinics, claims, telemetry, and policy documents in this repository are 100% synthetic data created for demonstration purposes.
