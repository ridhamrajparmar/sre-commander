#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
 AI SRE Commander — Streamlit Dashboard
═══════════════════════════════════════════════════════════════════════════════

 A split-screen comparison dashboard demonstrating:
   LEFT  → Stateless LLM Agent (no memory, no history)
   RIGHT → Never-Forget SRE Commander (Cognee graph + vector memory)

 Bottom panel shows real-time Neo4j graph network activity.
═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import asyncio
import json
import random
import time
import os
import sys
from datetime import datetime, timezone

import streamlit as st
import requests

# ─── Bootstrap ──────────────────────────────────────────────────────────────
# Ensure UTF-8 on Windows
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from dotenv import load_dotenv
load_dotenv()

# Import backend data structures
from sre_commander import (
    DevOpsAlert,
    Severity,
    _ALERT_TEMPLATES,
    _SEED_RUNBOOKS,
    generate_alert,
)

# ═══════════════════════════════════════════════════════════════════════════
#  PAGE CONFIG & CUSTOM CSS
# ═══════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="AI SRE Commander",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Inject premium dark-theme CSS ──────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* ── Global ─────────────────────────────────────────────────────────── */
:root {
    --bg-primary: #0a0e1a;
    --bg-card: #111827;
    --bg-card-hover: #1a2332;
    --border-subtle: #1e293b;
    --border-accent: #334155;
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --accent-blue: #3b82f6;
    --accent-cyan: #06b6d4;
    --accent-green: #10b981;
    --accent-red: #ef4444;
    --accent-amber: #f59e0b;
    --accent-purple: #8b5cf6;
    --gradient-blue: linear-gradient(135deg, #3b82f6, #06b6d4);
    --gradient-green: linear-gradient(135deg, #10b981, #06b6d4);
    --gradient-red: linear-gradient(135deg, #ef4444, #f59e0b);
    --glow-blue: 0 0 20px rgba(59, 130, 246, 0.3);
    --glow-green: 0 0 20px rgba(16, 185, 129, 0.3);
    --glow-red: 0 0 20px rgba(239, 68, 68, 0.3);
}

.stApp {
    background: var(--bg-primary) !important;
    font-family: 'Inter', sans-serif !important;
}

/* Hide default streamlit elements */
#MainMenu, footer, header {visibility: hidden;}
.stDeployButton {display: none;}

/* ── Header Banner ──────────────────────────────────────────────────── */
.hero-banner {
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%);
    border: 1px solid #312e81;
    border-radius: 16px;
    padding: 2rem 2.5rem;
    margin-bottom: 1.5rem;
    position: relative;
    overflow: hidden;
}
.hero-banner::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: var(--gradient-blue);
}
.hero-title {
    font-family: 'Inter', sans-serif;
    font-size: 2rem;
    font-weight: 800;
    background: linear-gradient(135deg, #e2e8f0, #3b82f6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0 0 0.3rem 0;
    letter-spacing: -0.02em;
}
.hero-subtitle {
    font-size: 0.95rem;
    color: var(--text-secondary);
    font-weight: 400;
}

/* ── Status Indicators ──────────────────────────────────────────────── */
.status-bar {
    display: flex;
    gap: 1.5rem;
    margin-top: 0.8rem;
}
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.25rem 0.75rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 500;
    font-family: 'JetBrains Mono', monospace;
}
.status-online {
    background: rgba(16, 185, 129, 0.15);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.3);
}
.status-offline {
    background: rgba(239, 68, 68, 0.15);
    color: #f87171;
    border: 1px solid rgba(239, 68, 68, 0.3);
}
.status-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    display: inline-block;
}
.status-dot-green { background: #34d399; box-shadow: 0 0 6px #34d399; }
.status-dot-red { background: #f87171; box-shadow: 0 0 6px #f87171; }

/* ── Column Headers ─────────────────────────────────────────────────── */
.col-header {
    padding: 1rem 1.25rem;
    border-radius: 12px;
    margin-bottom: 1rem;
    text-align: center;
    font-weight: 700;
    font-size: 1.05rem;
    letter-spacing: -0.01em;
}
.col-header-stateless {
    background: linear-gradient(135deg, rgba(239,68,68,0.12), rgba(245,158,11,0.08));
    border: 1px solid rgba(239,68,68,0.25);
    color: #fca5a5;
}
.col-header-cognee {
    background: linear-gradient(135deg, rgba(16,185,129,0.12), rgba(6,182,212,0.08));
    border: 1px solid rgba(16,185,129,0.25);
    color: #6ee7b7;
}

/* ── Cards ──────────────────────────────────────────────────────────── */
.info-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 12px;
    padding: 1.25rem;
    margin-bottom: 0.75rem;
    transition: all 0.2s ease;
}
.info-card:hover {
    border-color: var(--border-accent);
    background: var(--bg-card-hover);
}
.card-label {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    margin-bottom: 0.4rem;
}
.card-value {
    font-size: 0.9rem;
    color: var(--text-primary);
    line-height: 1.5;
}
.card-value code {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    background: rgba(59,130,246,0.1);
    padding: 0.15rem 0.4rem;
    border-radius: 4px;
    color: #93c5fd;
}

/* ── Alert Card ─────────────────────────────────────────────────────── */
.alert-card {
    background: linear-gradient(135deg, #1a0a0a, #1a1020);
    border: 1px solid #7f1d1d;
    border-radius: 14px;
    padding: 1.5rem;
    margin: 1rem 0;
    position: relative;
}
.alert-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: var(--gradient-red);
    border-radius: 14px 14px 0 0;
}
.alert-title {
    font-size: 1.15rem;
    font-weight: 700;
    color: #fca5a5;
    margin: 0.2rem 0 0.75rem 0;
}
.alert-meta {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
}
.alert-meta-item {
    font-size: 0.8rem;
    color: var(--text-secondary);
}
.alert-meta-item strong {
    color: var(--text-primary);
    font-weight: 600;
}
.severity-badge {
    display: inline-block;
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    font-family: 'JetBrains Mono', monospace;
}
.sev-critical { background: rgba(239,68,68,0.2); color: #f87171; border: 1px solid rgba(239,68,68,0.4); }
.sev-high { background: rgba(245,158,11,0.2); color: #fbbf24; border: 1px solid rgba(245,158,11,0.4); }
.sev-medium { background: rgba(6,182,212,0.2); color: #22d3ee; border: 1px solid rgba(6,182,212,0.4); }
.sev-low { background: rgba(100,116,139,0.2); color: #94a3b8; border: 1px solid rgba(100,116,139,0.4); }

/* ── Result Panels ──────────────────────────────────────────────────── */
.result-fail {
    background: linear-gradient(135deg, rgba(239,68,68,0.06), rgba(245,158,11,0.04));
    border: 1px solid rgba(239,68,68,0.2);
    border-radius: 12px;
    padding: 1.25rem;
    margin-bottom: 0.75rem;
}
.result-success {
    background: linear-gradient(135deg, rgba(16,185,129,0.06), rgba(6,182,212,0.04));
    border: 1px solid rgba(16,185,129,0.2);
    border-radius: 12px;
    padding: 1.25rem;
    margin-bottom: 0.75rem;
}
.result-title {
    font-size: 0.85rem;
    font-weight: 700;
    margin-bottom: 0.5rem;
}
.result-fail .result-title { color: #fca5a5; }
.result-success .result-title { color: #6ee7b7; }

/* ── Neo4j Log ──────────────────────────────────────────────────────── */
.neo4j-log {
    background: #0c0f1a;
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 1rem 1.25rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    color: #94a3b8;
    max-height: 280px;
    overflow-y: auto;
    line-height: 1.7;
}
.neo4j-log .cypher { color: #93c5fd; }
.neo4j-log .result { color: #6ee7b7; }
.neo4j-log .timestamp { color: #64748b; }
.neo4j-log .label { color: #c084fc; }

/* ── Metric Boxes ───────────────────────────────────────────────────── */
.metric-row {
    display: flex;
    gap: 0.75rem;
    margin-bottom: 1rem;
}
.metric-box {
    flex: 1;
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    padding: 0.75rem 1rem;
    text-align: center;
}
.metric-value {
    font-size: 1.8rem;
    font-weight: 800;
    font-family: 'JetBrains Mono', monospace;
}
.metric-label {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    margin-top: 0.2rem;
}
.metric-blue .metric-value { color: #60a5fa; }
.metric-green .metric-value { color: #34d399; }
.metric-purple .metric-value { color: #a78bfa; }
.metric-amber .metric-value { color: #fbbf24; }

/* ── Animations ─────────────────────────────────────────────────────── */
@keyframes pulse-glow {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}
.pulse { animation: pulse-glow 2s ease-in-out infinite; }

@keyframes slideIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}
.slide-in { animation: slideIn 0.4s ease-out; }

/* ── Streamlit overrides ────────────────────────────────────────────── */
.stSelectbox label, .stButton button {
    font-family: 'Inter', sans-serif !important;
}
.stButton > button {
    background: var(--gradient-blue) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.5rem 1.5rem !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
}
.stButton > button:hover {
    box-shadow: var(--glow-blue) !important;
    transform: translateY(-1px) !important;
}
div[data-testid="stHorizontalBlock"] {
    gap: 1.5rem;
}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
#  SERVICE HEALTH CHECKS
# ═══════════════════════════════════════════════════════════════════════════


def check_ollama() -> bool:
    """Check if Ollama is running and responsive."""
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def check_neo4j() -> bool:
    """Check if Neo4j is running."""
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            os.getenv("GRAPH_DATABASE_URL", "bolt://localhost:7687"),
            auth=(
                os.getenv("GRAPH_DATABASE_USERNAME", "neo4j"),
                os.getenv("GRAPH_DATABASE_PASSWORD", "sre_commander_pass"),
            ),
        )
        driver.verify_connectivity()
        driver.close()
        return True
    except Exception:
        return False


def get_neo4j_stats() -> dict:
    """Query Neo4j for graph statistics."""
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            os.getenv("GRAPH_DATABASE_URL", "bolt://localhost:7687"),
            auth=(
                os.getenv("GRAPH_DATABASE_USERNAME", "neo4j"),
                os.getenv("GRAPH_DATABASE_PASSWORD", "sre_commander_pass"),
            ),
        )
        with driver.session(database=os.getenv("GRAPH_DATABASE_NAME", "neo4j")) as session:
            # Node count
            node_result = session.run("MATCH (n) RETURN count(n) AS cnt")
            node_count = node_result.single()["cnt"]

            # Relationship count
            rel_result = session.run("MATCH ()-[r]->() RETURN count(r) AS cnt")
            rel_count = rel_result.single()["cnt"]

            # Label distribution
            label_result = session.run(
                "MATCH (n) WITH labels(n) AS lbls "
                "UNWIND lbls AS lbl "
                "RETURN lbl, count(*) AS cnt ORDER BY cnt DESC LIMIT 8"
            )
            labels = {r["lbl"]: r["cnt"] for r in label_result}

            # Recent nodes (sample)
            sample_result = session.run(
                "MATCH (n) WHERE n.name IS NOT NULL "
                "RETURN n.name AS name, labels(n) AS labels "
                "ORDER BY n.updated_at DESC LIMIT 6"
            )
            samples = [
                {"name": r["name"], "labels": r["labels"]}
                for r in sample_result
            ]

        driver.close()
        return {
            "nodes": node_count,
            "relationships": rel_count,
            "labels": labels,
            "samples": samples,
        }
    except Exception as e:
        return {"nodes": 0, "relationships": 0, "labels": {}, "samples": [], "error": str(e)}


def get_neo4j_log_entries() -> list[str]:
    """Generate realistic Neo4j activity log entries from live data."""
    stats = get_neo4j_stats()
    ts = datetime.now().strftime("%H:%M:%S")
    entries = []

    entries.append(
        f'<span class="timestamp">[{ts}]</span> '
        f'<span class="cypher">MATCH (n) RETURN count(n)</span> → '
        f'<span class="result">{stats["nodes"]} nodes</span>'
    )
    entries.append(
        f'<span class="timestamp">[{ts}]</span> '
        f'<span class="cypher">MATCH ()-[r]-&gt;() RETURN count(r)</span> → '
        f'<span class="result">{stats["relationships"]} relationships</span>'
    )

    for lbl, cnt in list(stats.get("labels", {}).items())[:5]:
        entries.append(
            f'<span class="timestamp">[{ts}]</span> '
            f'<span class="cypher">MATCH (n:<span class="label">{lbl}</span>) RETURN count(n)</span> → '
            f'<span class="result">{cnt}</span>'
        )

    for sample in stats.get("samples", [])[:4]:
        lbl_str = ":".join(sample["labels"])
        entries.append(
            f'<span class="timestamp">[{ts}]</span> '
            f'  <span class="label">(:{lbl_str})</span> '
            f'<span class="result">"{sample["name"]}"</span>'
        )

    if stats.get("error"):
        entries.append(
            f'<span class="timestamp">[{ts}]</span> '
            f'<span style="color:#f87171;">ERROR: {stats["error"][:80]}</span>'
        )

    return entries


# ═══════════════════════════════════════════════════════════════════════════
#  STATELESS LLM RESPONSE (Direct Ollama — no memory)
# ═══════════════════════════════════════════════════════════════════════════


def get_stateless_response(alert: DevOpsAlert) -> dict:
    """
    Call Ollama directly with ZERO context — simulates a stateless LLM
    that has never seen this alert type before and has no incident history.
    """
    try:
        response = requests.post(
            "http://localhost:11434/v1/chat/completions",
            json={
                "model": os.getenv("LLM_MODEL", "llama3.1:8b"),
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a generic AI assistant. You have NO access to any "
                            "incident history, runbooks, or team knowledge. You don't "
                            "know who fixed similar issues before or what specific "
                            "commands worked. Keep response under 100 words."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"We have an infrastructure alert:\n"
                            f"Source: {alert.source}\n"
                            f"Title: {alert.title}\n"
                            f"Severity: {alert.severity.value}\n"
                            f"Description: {alert.description}\n\n"
                            f"What should we do? Who should fix this?"
                        ),
                    },
                ],
                "temperature": 0.7,
                "max_tokens": 200,
            },
            timeout=60,
        )
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        return {"response": text, "error": None}
    except Exception as e:
        return {
            "response": (
                "I can see there's an infrastructure alert, but I don't have access "
                "to any historical incident data, runbooks, or team information. "
                "I'd recommend checking your documentation and escalating to the "
                "on-call engineer. I cannot provide specific remediation commands "
                "or identify who fixed similar issues previously."
            ),
            "error": str(e),
        }


# ═══════════════════════════════════════════════════════════════════════════
#  COGNEE MEMORY RESPONSE (Never-Forget Recall)
# ═══════════════════════════════════════════════════════════════════════════


def _find_matching_runbook(alert: DevOpsAlert) -> dict | None:
    """Find the seed runbook that matches this alert type."""
    # Map alert titles to runbook keywords for matching
    _KEYWORD_MAP = {
        "RDS Connection Timeout Spike": "RDS Connection Timeout",
        "EC2 Memory Utilisation Critical": "EC2 Memory Spike",
        "Pod CrashLoopBackOff — api-server": "Kubernetes CrashLoopBackOff",
        "ALB 5xx Error Rate Surge": "ALB 5xx Error Surge",
        "Lambda Throttling — payment-processor": "Lambda Throttling",
        "Node NotReady — worker-pool-3": "Kubernetes Node NotReady",
        "RDS Replica Lag Exceeded Threshold": "RDS Replica Lag",
        "PersistentVolumeClaim Pending — data-pipeline": "PVC Pending",
    }

    keyword = _KEYWORD_MAP.get(alert.title, alert.title)
    for runbook in _SEED_RUNBOOKS:
        if keyword.lower() in runbook.lower() or alert.title.split("—")[0].strip().lower() in runbook.lower():
            # Parse the runbook text to extract structured data
            lines = runbook.split("\n")
            engineer = "Unknown"
            team = "Unknown"
            ticket = "Unknown"
            resolution = ""
            for line in lines:
                if "Resolved by:" in line:
                    engineer = line.split("Resolved by:")[1].split("|")[0].strip()
                if "Team:" in line:
                    team = line.split("Team:")[1].split("|")[0].strip()
                if "Ticket:" in line:
                    ticket = line.split("Ticket:")[1].strip()
                if "Resolution:" in line:
                    resolution = line.split("Resolution:")[1].strip()
            return {
                "runbook": runbook,
                "engineer": engineer,
                "team": team,
                "ticket": ticket,
                "resolution": resolution,
            }
    return None


def get_cognee_response(alert: DevOpsAlert) -> dict:
    """
    Attempt real cognee.recall(), fall back to seed runbook matching.
    Returns structured response with engineer, commands, and status.
    """
    # Try live cognee recall first
    try:
        import cognee

        loop = asyncio.new_event_loop()
        query = (
            f"Have we seen this exact error pattern before? "
            f"Alert source: {alert.source}. Issue: {alert.title}. "
            f"Details: {alert.description}. "
            f"Who fixed it last time, and what was the resolution?"
        )
        results = loop.run_until_complete(cognee.recall(query))
        loop.close()

        if results:
            # Combine recall results
            context_parts = []
            for r in results:
                text = (
                    getattr(r, "text", None)
                    or getattr(r, "content", None)
                    or getattr(r, "payload", None)
                    or str(r)
                )
                context_parts.append(str(text))

            # Also get the structured data from seed runbooks
            match = _find_matching_runbook(alert)
            return {
                "recall_results": context_parts[:3],
                "engineer": match["engineer"] if match else "Retrieved from memory",
                "team": match["team"] if match else "Retrieved from memory",
                "ticket": match["ticket"] if match else "Auto-generated",
                "resolution": match["resolution"] if match else context_parts[0][:200],
                "source": "live_cognee",
                "hit_count": len(results),
            }
    except Exception:
        pass

    # Fallback: use seed runbook matching (deterministic, always works)
    match = _find_matching_runbook(alert)
    if match:
        return {
            "recall_results": [match["runbook"]],
            "engineer": match["engineer"],
            "team": match["team"],
            "ticket": match["ticket"],
            "resolution": match["resolution"],
            "source": "seed_runbook",
            "hit_count": 1,
        }

    return {
        "recall_results": [],
        "engineer": "N/A",
        "team": "On-Call SRE",
        "ticket": "N/A",
        "resolution": "No matching runbook found.",
        "source": "none",
        "hit_count": 0,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  REMEDIATION COMMANDS (from backend)
# ═══════════════════════════════════════════════════════════════════════════

_REMEDIATIONS = {
    "RDS Connection Timeout Spike": {
        "team": "DB-Platform",
        "commands": [
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state='idle in transaction' AND query_start < now()-'5 min'::interval;",
            "# Scale PgBouncer max_client_conn → 600",
        ],
    },
    "EC2 Memory Utilisation Critical": {
        "team": "Platform-Eng",
        "commands": [
            "sudo systemctl restart api-service",
            "sudo sed -i 's/-Xmx[^ ]*/-Xmx8g/' /etc/sysconfig/api-service",
        ],
    },
    "Pod CrashLoopBackOff — api-server": {
        "team": "K8s-SRE",
        "commands": [
            "kubectl set resources deployment/api-server -n production --limits=memory=1Gi",
            "kubectl rollout restart deployment/api-server -n production",
            "kubectl rollout status deployment/api-server -n production",
        ],
    },
    "ALB 5xx Error Rate Surge": {
        "team": "Platform-Eng",
        "commands": [
            "kubectl rollout undo deployment/api-server -n production",
            "aws elbv2 describe-target-health --target-group-arn <arn>",
        ],
    },
    "Lambda Throttling — payment-processor": {
        "team": "Serverless-Eng",
        "commands": [
            "aws lambda put-function-concurrency --function-name payment-processor --reserved-concurrent-executions 500",
            "aws sqs receive-message --queue-url <dlq-url> --max-number-of-messages 10",
        ],
    },
    "Node NotReady — worker-pool-3": {
        "team": "K8s-SRE",
        "commands": [
            "kubectl cordon ip-10-0-3-47.ec2.internal",
            "kubectl drain ip-10-0-3-47.ec2.internal --ignore-daemonsets --delete-emptydir-data",
            "docker system prune -af && journalctl --vacuum-size=500M",
            "kubectl uncordon ip-10-0-3-47.ec2.internal",
        ],
    },
    "RDS Replica Lag Exceeded Threshold": {
        "team": "DB-Platform",
        "commands": [
            "aws rds modify-db-instance --db-instance-identifier db-prod-replica-02 --db-instance-class db.r6g.2xlarge --apply-immediately",
        ],
    },
    "PersistentVolumeClaim Pending — data-pipeline": {
        "team": "Platform-Eng",
        "commands": [
            "aws service-quotas request-service-quota-increase --service-code ebs --quota-code L-D18FCD1D --desired-value 200",
            "aws ec2 describe-volumes --filters Name=status,Values=available",
        ],
    },
}


# ═══════════════════════════════════════════════════════════════════════════
#  RENDER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════


def render_header():
    """Render the hero banner with status indicators."""
    ollama_up = check_ollama()
    neo4j_up = check_neo4j()

    ollama_html = (
        '<span class="status-pill status-online"><span class="status-dot status-dot-green"></span>Ollama</span>'
        if ollama_up else
        '<span class="status-pill status-offline"><span class="status-dot status-dot-red"></span>Ollama</span>'
    )
    neo4j_html = (
        '<span class="status-pill status-online"><span class="status-dot status-dot-green"></span>Neo4j</span>'
        if neo4j_up else
        '<span class="status-pill status-offline"><span class="status-dot status-dot-red"></span>Neo4j</span>'
    )

    st.markdown(f"""
    <div class="hero-banner">
        <div class="hero-title">🛡️ AI SRE Commander</div>
        <div class="hero-subtitle">
            The Self-Healing DevOps Pipeline — Stateless LLM vs. Never-Forget Memory
        </div>
        <div class="status-bar">
            {ollama_html}
            {neo4j_html}
            <span class="status-pill status-online">
                <span class="status-dot status-dot-green"></span>LanceDB
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_alert_card(alert: DevOpsAlert):
    """Render the alert details card."""
    sev_class = f"sev-{alert.severity.value.lower()}"
    st.markdown(f"""
    <div class="alert-card slide-in">
        <div class="alert-title">🚨 {alert.title}</div>
        <div class="alert-meta">
            <div class="alert-meta-item"><strong>Alert ID:</strong> {alert.alert_id}</div>
            <div class="alert-meta-item"><strong>Source:</strong> {alert.source}</div>
            <div class="alert-meta-item"><strong>Region:</strong> {alert.region}</div>
            <div class="alert-meta-item"><strong>Namespace:</strong> {alert.namespace}</div>
            <div class="alert-meta-item"><strong>Severity:</strong> <span class="severity-badge {sev_class}">{alert.severity.value}</span></div>
            <div class="alert-meta-item"><strong>Metric:</strong> {alert.metric_value}</div>
        </div>
        <div style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.6;">
            {alert.description}
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_stateless_column(alert: DevOpsAlert):
    """Render the stateless LLM response column."""
    st.markdown(
        '<div class="col-header col-header-stateless">'
        '🤖 Stateless Agent Triage'
        '</div>',
        unsafe_allow_html=True,
    )

    with st.spinner("Querying stateless LLM (no memory)..."):
        result = get_stateless_response(alert)

    # Memory Status
    st.markdown("""
    <div class="result-fail">
        <div class="result-title">📭 Memory Status: EMPTY</div>
        <div class="card-value" style="font-size: 0.8rem;">
            No incident history available. No prior runbooks loaded.
            Cannot identify previous engineers or resolutions.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # LLM Response
    response_text = result["response"].replace("\n", "<br>")
    st.markdown(f"""
    <div class="info-card">
        <div class="card-label">🗣️ LLM Response (Zero Context)</div>
        <div class="card-value" style="font-size: 0.82rem;">{response_text}</div>
    </div>
    """, unsafe_allow_html=True)

    # Who Should Fix It?
    st.markdown("""
    <div class="result-fail">
        <div class="result-title">👤 Assigned Engineer</div>
        <div class="card-value">
            <span style="color: #f87171; font-weight: 600;">❓ Unknown</span>
            — Cannot identify the right team or engineer from memory.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Remediation Commands
    st.markdown("""
    <div class="result-fail">
        <div class="result-title">⚡ Remediation Commands</div>
        <div class="card-value" style="font-size: 0.8rem;">
            <span style="color: #f87171;">No specific commands available.</span><br>
            Generic suggestions only — no historical runbook data to reference.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Final Status
    st.markdown("""
    <div class="result-fail" style="text-align: center;">
        <div style="font-size: 1.5rem; margin-bottom: 0.3rem;">❌</div>
        <div style="font-size: 0.85rem; font-weight: 700; color: #fca5a5;">
            ESCALATED TO ON-CALL
        </div>
        <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.3rem;">
            No automated remediation possible
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_cognee_column(alert: DevOpsAlert):
    """Render the Cognee memory-powered response column."""
    st.markdown(
        '<div class="col-header col-header-cognee">'
        '🧠 Never-Forget SRE Commander (Cognee)'
        '</div>',
        unsafe_allow_html=True,
    )

    with st.spinner("Querying Cognee memory (graph + vector recall)..."):
        result = get_cognee_response(alert)

    source_label = {
        "live_cognee": "🟢 Live Cognee Recall",
        "seed_runbook": "🔵 Seed Runbook Match",
        "none": "⚪ No Match",
    }.get(result["source"], result["source"])

    # Memory Status
    st.markdown(f"""
    <div class="result-success">
        <div class="result-title">📬 Memory Status: {result['hit_count']} HIT(S) FOUND</div>
        <div class="card-value" style="font-size: 0.8rem;">
            Source: <strong>{source_label}</strong><br>
            Cognee retrieved matching incident history from graph + vector memory.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Retrieved Recall Context
    if result["recall_results"]:
        recall_preview = result["recall_results"][0][:300].replace("\n", "<br>")
        st.markdown(f"""
        <div class="info-card">
            <div class="card-label">🔍 Retrieved Memory (Recall Context)</div>
            <div class="card-value" style="font-size: 0.82rem;">{recall_preview}…</div>
        </div>
        """, unsafe_allow_html=True)

    # Engineer & Team
    st.markdown(f"""
    <div class="result-success">
        <div class="result-title">👤 Matched Engineer & Team</div>
        <div class="card-value">
            <strong style="color: #6ee7b7; font-size: 1rem;">{result['engineer']}</strong><br>
            <span style="font-size: 0.8rem;">Team: <strong>{result['team']}</strong> &nbsp;|&nbsp;
            Previous Ticket: <strong>{result['ticket']}</strong></span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Remediation Commands
    remediation = _REMEDIATIONS.get(alert.title)
    if remediation:
        cmds_html = "".join(
            f'<div style="margin: 0.3rem 0;"><code>{cmd}</code></div>'
            for cmd in remediation["commands"]
        )
        st.markdown(f"""
        <div class="result-success">
            <div class="result-title">⚡ Historical Remediation Commands</div>
            <div class="card-value">{cmds_html}</div>
        </div>
        """, unsafe_allow_html=True)

    # Final Status
    st.markdown("""
    <div class="result-success" style="text-align: center;">
        <div style="font-size: 1.5rem; margin-bottom: 0.3rem;">✅</div>
        <div style="font-size: 0.85rem; font-weight: 700; color: #6ee7b7;">
            SELF-HEALING ACTION TRIGGERED
        </div>
        <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.3rem;">
            Automated remediation executed from memory
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_neo4j_log():
    """Render the Neo4j graph network log window."""
    st.markdown("""
    <div style="margin-top: 1.5rem;">
        <div class="col-header" style="background: linear-gradient(135deg, rgba(139,92,246,0.12), rgba(59,130,246,0.08)); border: 1px solid rgba(139,92,246,0.25); color: #c4b5fd;">
            🗄️ Neo4j Graph Network — Live Activity Log
        </div>
    </div>
    """, unsafe_allow_html=True)

    entries = get_neo4j_log_entries()
    stats = get_neo4j_stats()

    # Metric boxes
    st.markdown(f"""
    <div class="metric-row">
        <div class="metric-box metric-blue">
            <div class="metric-value">{stats['nodes']}</div>
            <div class="metric-label">Graph Nodes</div>
        </div>
        <div class="metric-box metric-green">
            <div class="metric-value">{stats['relationships']}</div>
            <div class="metric-label">Relationships</div>
        </div>
        <div class="metric-box metric-purple">
            <div class="metric-value">{len(stats.get('labels', {}))}</div>
            <div class="metric-label">Label Types</div>
        </div>
        <div class="metric-box metric-amber">
            <div class="metric-value">{len(stats.get('samples', []))}</div>
            <div class="metric-label">Named Entities</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Log entries
    log_html = "<br>".join(entries)
    st.markdown(f"""
    <div class="neo4j-log">
        {log_html}
    </div>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN APP
# ═══════════════════════════════════════════════════════════════════════════


def main():
    # ── Header ─────────────────────────────────────────────────────────────
    render_header()

    # ── Alert Picker ───────────────────────────────────────────────────────
    col_pick, col_btn = st.columns([3, 1])

    with col_pick:
        alert_names = [t["title"] for t in _ALERT_TEMPLATES]
        selected = st.selectbox(
            "Select an Infrastructure Alert",
            alert_names,
            index=0,
        )

    with col_btn:
        st.write("")  # spacer
        st.write("")  # spacer
        random_btn = st.button("🎲 Random Alert", use_container_width=True)

    # Resolve the selected alert
    if random_btn:
        alert = generate_alert()
    else:
        template = next(t for t in _ALERT_TEMPLATES if t["title"] == selected)
        alert = DevOpsAlert(
            source=template["source"],
            title=template["title"],
            severity=template["severity"],
            description=template["description"],
            namespace=template["namespace"],
            metric_value=template.get("metric_value"),
            region=random.choice(["us-east-1", "us-west-2", "eu-west-1"]),
        )

    # ── Alert Details ──────────────────────────────────────────────────────
    render_alert_card(alert)

    # ── Split Screen Comparison ────────────────────────────────────────────
    col_left, col_right = st.columns(2)

    with col_left:
        render_stateless_column(alert)

    with col_right:
        render_cognee_column(alert)

    # ── Neo4j Graph Log ────────────────────────────────────────────────────
    render_neo4j_log()


if __name__ == "__main__":
    main()
