"""Gemini-powered Agentic Data & Document Agent using the google-genai SDK.

Designed to be clean, readable, and easy for commercial FSRs/CEs to walk through
live on stage in under 3 minutes while demonstrating real enterprise tool calling,
SQL guardrails, document grounding, and auditable execution traces.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from google import genai
from google.genai import types

from app.data_layer import EnterpriseDataLayer, UnsafeSQLError
from app.docs_corpus import search_policy_docs

DEFAULT_MODEL = "gemini-3-flash-preview"
MAX_TOOL_ROUNDS = 10


class AgentConfigurationError(RuntimeError):
    """Raised when neither Vertex AI nor Gemini API credentials are configured."""


def compute_recovery_plan(
    revenue_at_risk_usd: float,
    recoverable_pct: float,
    implementation_cost_usd: float,
    action_summary: str,
) -> dict[str, Any]:
    """Deterministically calculate expected dollar recovery and ROI for an executive action."""
    pct = max(0.0, min(100.0, float(recoverable_pct)))
    expected_recovery = round(float(revenue_at_risk_usd) * (pct / 100.0), 2)
    net_impact = round(expected_recovery - float(implementation_cost_usd), 2)
    roi_multiple = (
        round(expected_recovery / float(implementation_cost_usd), 2)
        if implementation_cost_usd > 0
        else None
    )
    return {
        "revenue_at_risk_usd": round(float(revenue_at_risk_usd), 2),
        "recoverable_pct": pct,
        "expected_recovery_usd": expected_recovery,
        "implementation_cost_usd": round(float(implementation_cost_usd), 2),
        "net_impact_usd": net_impact,
        "roi_multiple": roi_multiple,
        "action_summary": action_summary,
    }


def _build_tool_declarations() -> list[types.Tool]:
    """Declare the three enterprise tools available to Gemini."""
    return [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="run_readonly_sql",
                    description=(
                        "Execute a read-only SELECT/WITH SQL query against the enterprise "
                        "operations database (clinics, exam_volume_daily, payer_claims, "
                        "equipment_telemetry). Use this to verify exact metrics, trends, "
                        "denial rates, SLA breaches, and equipment uptime."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "sql_query": types.Schema(
                                type=types.Type.STRING,
                                description="Valid read-only SELECT or WITH SQL query.",
                            ),
                            "rationale": types.Schema(
                                type=types.Type.STRING,
                                description="Short business reason for running this query.",
                            ),
                        },
                        required=["sql_query", "rationale"],
                    ),
                ),
                types.FunctionDeclaration(
                    name="search_policy_docs",
                    description=(
                        "Search unstructured enterprise documents (payer reimbursement rules, "
                        "vendor maintenance SLA contracts, turnaround playbooks, and LGPD "
                        "governance policies) to explain root causes and contractual remedies."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "query": types.Schema(
                                type=types.Type.STRING,
                                description="Keywords describing the policy, payer, vendor, or SLA topic.",
                            ),
                        },
                        required=["query"],
                    ),
                ),
                types.FunctionDeclaration(
                    name="compute_recovery_plan",
                    description=(
                        "Deterministically compute expected USD recovery, net impact, and ROI "
                        "for a proposed operational or commercial remediation action."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "revenue_at_risk_usd": types.Schema(type=types.Type.NUMBER),
                            "recoverable_pct": types.Schema(type=types.Type.NUMBER),
                            "implementation_cost_usd": types.Schema(type=types.Type.NUMBER),
                            "action_summary": types.Schema(type=types.Type.STRING),
                        },
                        required=[
                            "revenue_at_risk_usd",
                            "recoverable_pct",
                            "implementation_cost_usd",
                            "action_summary",
                        ],
                    ),
                ),
            ]
        )
    ]


class EnterpriseAIAgent:
    """Orchestrates Gemini function calling over structured SQL + unstructured policies."""

    def __init__(self, data_layer: EnterpriseDataLayer) -> None:
        self.data_layer = data_layer
        self.model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)

    def get_auth_status(self) -> dict[str, Any]:
        """Inspect active Vertex AI / Gemini API configuration without faking readiness."""
        use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true", "yes")
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
        api_key = os.getenv("GEMINI_API_KEY")

        if use_vertex and project:
            return {
                "ready": True,
                "mode": "vertex_ai",
                "project": project,
                "location": location,
                "model": self.model,
            }
        if api_key:
            return {
                "ready": True,
                "mode": "gemini_api_key",
                "project": project,
                "location": None,
                "model": self.model,
            }
        return {
            "ready": False,
            "mode": "unconfigured",
            "project": project,
            "location": location,
            "model": self.model,
            "setup_hint": (
                "Export GOOGLE_GENAI_USE_VERTEXAI=true and GOOGLE_CLOUD_PROJECT=<your-project> "
                "(with gcloud ADC), OR export GEMINI_API_KEY=<your-key>."
            ),
        }

    def _create_client(self) -> genai.Client:
        status = self.get_auth_status()
        if not status["ready"]:
            raise AgentConfigurationError(status["setup_hint"])

        if status["mode"] == "vertex_ai":
            return genai.Client(
                vertexai=True,
                project=status["project"],
                location=status["location"],
            )
        return genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    def _build_system_instruction(self) -> str:
        schema_json = json.dumps(self.data_layer.get_schema_summary(), indent=2)
        return (
            "You are an Enterprise AI Operations & Revenue Agent for a multi-unit diagnostic "
            "imaging network. Your job is to answer executive questions by combining:\n"
            "1. Live SQL analytics via `run_readonly_sql` (never invent numbers).\n"
            "2. Unstructured contractual/policy rules via `search_policy_docs` (always cite `doc_id`).\n"
            "3. Deterministic financial impact via `compute_recovery_plan` when proposing actions.\n\n"
            "Rules:\n"
            "- Always query the database first before stating any financial or operational figure.\n"
            "- Cross-reference anomalies with `search_policy_docs` to explain WHY they occurred.\n"
            "- Structure your final answer clearly in Markdown with: Executive Summary, "
            "Verified Data Findings, Policy & Contract Citations, and Prioritized Action Plan.\n"
            "- Keep responses concise, executive-ready, and grounded strictly in tool outputs.\n\n"
            "Known categorical values (exact case):\n"
            "- payer_claims.status: 'APPROVED', 'DENIED'\n"
            "- payer_claims.denial_reason: 'MISSING_PRE_AUTH', 'DUPLICATE_CODE', 'EXPIRED_PROTOCOL', 'NONE'\n"
            "- equipment_telemetry.alert_status: 'HEALTHY', 'WATCH', 'SLA_BREACH'\n"
            "- modality: 'MRI', 'CT_SCAN', 'PET_CT', 'ULTRASOUND'\n\n"
            f"Database Schema ({self.data_layer.backend}):\n{schema_json}"
        )

    def _dispatch_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "run_readonly_sql":
            try:
                return self.data_layer.execute_readonly_sql(args.get("sql_query", ""))
            except UnsafeSQLError as exc:
                return {"error": f"GUARDRAIL_BLOCKED: {exc}"}
            except Exception as exc:  # noqa: BLE001
                return {"error": f"SQL_EXECUTION_ERROR: {exc}"}
        if name == "search_policy_docs":
            return search_policy_docs(args.get("query", ""))
        if name == "compute_recovery_plan":
            return compute_recovery_plan(
                revenue_at_risk_usd=float(args.get("revenue_at_risk_usd", 0)),
                recoverable_pct=float(args.get("recoverable_pct", 0)),
                implementation_cost_usd=float(args.get("implementation_cost_usd", 0)),
                action_summary=str(args.get("action_summary", "")),
            )
        return {"error": f"Unknown tool: {name}"}

    def ask(self, question: str) -> dict[str, Any]:
        """Run the multi-step Gemini tool-calling loop and return answer + full trace."""
        t0 = time.perf_counter()
        client = self._create_client()
        tools = _build_tool_declarations()
        config = types.GenerateContentConfig(
            system_instruction=self._build_system_instruction(),
            tools=tools,
            temperature=0.1,
        )

        contents: list[types.Content] = [
            types.Content(role="user", parts=[types.Part.from_text(text=question)])
        ]
        trace: list[dict[str, Any]] = []
        final_text = ""

        for round_idx in range(1, MAX_TOOL_ROUNDS + 1):
            response = client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )

            candidate = response.candidates[0] if response.candidates else None
            if not candidate or not candidate.content or not candidate.content.parts:
                break

            contents.append(candidate.content)
            function_calls = [
                part.function_call
                for part in candidate.content.parts
                if getattr(part, "function_call", None)
            ]

            if not function_calls:
                final_text = response.text or ""
                break

            tool_response_parts: list[types.Part] = []
            for fc in function_calls:
                call_start = time.perf_counter()
                fc_args = dict(fc.args) if fc.args else {}
                result = self._dispatch_tool(fc.name, fc_args)
                duration_ms = round((time.perf_counter() - call_start) * 1000, 1)

                trace.append(
                    {
                        "round": round_idx,
                        "tool": fc.name,
                        "arguments": fc_args,
                        "status": "error" if "error" in result else "ok",
                        "duration_ms": duration_ms,
                        "result": result,
                    }
                )
                tool_response_parts.append(
                    types.Part.from_function_response(name=fc.name, response=result)
                )

            contents.append(types.Content(role="user", parts=tool_response_parts))

        return {
            "question": question,
            "answer_markdown": final_text,
            "trace": trace,
            "model": self.model,
            "backend": self.data_layer.backend,
            "total_duration_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
