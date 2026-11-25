"""Unstructured enterprise policy, SLA, and governance document corpus.

Provides deterministic keyword/relevance search with exact citation IDs so the
Gemini agent can cross-reference SQL anomalies with contractual and policy rules.
"""

from __future__ import annotations

import re
from typing import Any

POLICY_DOCUMENTS: list[dict[str, Any]] = [
    {
        "doc_id": "DOC-001",
        "title": "VidaPlus Saude — Q3/Q4 2026 Payer Reimbursement & Pre-Authorization Bulletin",
        "category": "Payer Policy",
        "effective_date": "2026-08-15",
        "tags": ["vidaplus", "payer", "denial", "claims", "mri", "pet_ct", "pre_auth", "revenue"],
        "content": (
            "Effective August 15, 2026, VidaPlus Saude updated its high-complexity imaging "
            "reimbursement rules. All MRI and PET_CT claims with billed value above $450 USD "
            "now require a verified digital pre-authorization token (TISS-AUTH-V4) attached "
            "prior to exam execution. Claims submitted without TISS-AUTH-V4 are automatically "
            "rejected with code MISSING_PRE_AUTH. Retroactive appeals are permitted within "
            "45 calendar days when clinical necessity documentation is attached; historical "
            "appeal recovery averages 78% of denied value. Automating pre-auth validation at "
            "scheduling eliminates >90% of future MISSING_PRE_AUTH denials."
        ),
    },
    {
        "doc_id": "DOC-002",
        "title": "MedTech Diagnostics — Master Equipment Maintenance SLA & Penalty Schedule",
        "category": "Vendor SLA",
        "effective_date": "2026-01-01",
        "tags": ["medtech", "equipment", "mri", "uptime", "downtime", "sla", "penalty", "campinas"],
        "content": (
            "Under Section 4.2 of the MedTech Diagnostics Master Service Agreement, all "
            "covered MRI, CT_SCAN, and PET_CT scanners carry a guaranteed 96.0% monthly "
            "uptime SLA and a maximum threshold of 12.0 unscheduled downtime hours per month. "
            "Whenever a covered device falls below 96.0% uptime OR exceeds 12.0 unscheduled "
            "downtime hours in a calendar month (status SLA_BREACH), the clinic is entitled "
            "to an automatic 15% service fee credit for that month (rising to 25% if the "
            "breach persists for two consecutive months) plus a mandatory 4-hour on-site "
            "senior engineer dispatch and loaner coil provisioning."
        ),
    },
    {
        "doc_id": "DOC-003",
        "title": "Clinical Turnaround SLA & Inter-Clinic Overflow Routing Playbook",
        "category": "Operations Policy",
        "effective_date": "2026-06-01",
        "tags": ["sla", "turnaround", "capacity", "overflow", "paulista", "morumbi", "campinas"],
        "content": (
            "Internal operational standards require routine imaging turnaround <= 24.0 hours "
            "and urgent imaging <= 4.0 hours. When any metro clinic exceeds 90% daily modality "
            "utilization or experiences >3 SLA breaches per day, scheduling ops should enable "
            "dynamic overflow routing to partner units within 15 km (for example, routing "
            "non-urgent MRI/CT overflow from Paulista Flagship CLN-SP01 to Morumbi Advanced "
            "Imaging CLN-SP02, which maintains spare evening capacity)."
        ),
    },
    {
        "doc_id": "DOC-004",
        "title": "Enterprise AI & LGPD Data Governance Standard for Commercial Analytics",
        "category": "Security & LGPD",
        "effective_date": "2026-07-01",
        "tags": ["lgpd", "security", "pii", "governance", "sql", "audit", "readonly", "ai"],
        "content": (
            "All generative AI agents operating over clinical or commercial datasets must "
            "enforce four mandatory controls: (1) Zero patient PII in LLM prompts — operate "
            "strictly on aggregated operational/financial tables; (2) Read-only SQL guardrails "
            "blocking all DML/DDL statements at the database driver and application layers; "
            "(3) Full tool-call trajectory audit logging (generated SQL, cited policy IDs, "
            "and timestamps); and (4) Human-in-the-loop sign-off before submitting external "
            "payer appeals or vendor SLA credit notices."
        ),
    },
]


def search_policy_docs(query: str, top_k: int = 3) -> dict[str, Any]:
    """Search unstructured policy documents and return ranked citations."""
    tokens = [t for t in re.findall(r"[a-z0-9_]+", query.lower()) if len(t) >= 2]
    scored: list[tuple[int, dict[str, Any]]] = []

    for doc in POLICY_DOCUMENTS:
        haystack = " ".join(
            [
                doc["doc_id"],
                doc["title"],
                doc["category"],
                " ".join(doc["tags"]),
                doc["content"],
            ]
        ).lower()
        score = sum(3 if t in doc["tags"] else (2 if t in doc["title"].lower() else 1) for t in tokens if t in haystack)
        if score > 0 or not tokens:
            scored.append((score, doc))

    scored.sort(key=lambda item: item[0], reverse=True)
    matches = [
        {
            "doc_id": doc["doc_id"],
            "title": doc["title"],
            "category": doc["category"],
            "effective_date": doc["effective_date"],
            "relevance_score": score,
            "excerpt": doc["content"],
        }
        for score, doc in scored[:top_k]
    ]
    return {"query": query, "match_count": len(matches), "documents": matches}


def list_all_policy_docs() -> list[dict[str, Any]]:
    """Return metadata and excerpts for all enterprise policy documents."""
    return [
        {
            "doc_id": d["doc_id"],
            "title": d["title"],
            "category": d["category"],
            "effective_date": d["effective_date"],
            "tags": d["tags"],
            "excerpt": d["content"],
        }
        for d in POLICY_DOCUMENTS
    ]
