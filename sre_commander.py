#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
 AI SRE Commander — The Self-Healing DevOps Pipeline
═══════════════════════════════════════════════════════════════════════════════

 An asynchronous Python workflow that:
   1. Ingests simulated DevOps alerts (CloudWatch-style)
   2. Queries cognee's hybrid graph-vector memory for past resolutions
   3. Simulates an automated triage / remediation action
   4. Learns from the outcome to permanently enrich the knowledge graph

 All inference is routed through a local Ollama instance — zero cloud deps.
═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import asyncio
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import cognee
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

# ─── Bootstrap ──────────────────────────────────────────────────────────────
load_dotenv()  # reads .env → cognee picks up LLM / DB env vars automatically

# Force UTF-8 on Windows to avoid UnicodeEncodeError with emoji in Rich output
import sys, os
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

console = Console()


# ═══════════════════════════════════════════════════════════════════════════
#  §1  MOCK ALERT CATALOGUE
# ═══════════════════════════════════════════════════════════════════════════


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class DevOpsAlert:
    """A simulated AWS CloudWatch / Kubernetes alert."""

    alert_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source: str = ""
    title: str = ""
    severity: Severity = Severity.HIGH
    description: str = ""
    region: str = "us-east-1"
    namespace: str = ""
    metric_value: Optional[float] = None


# ── Alert templates ────────────────────────────────────────────────────────
_ALERT_TEMPLATES: list[dict] = [
    {
        "source": "AWS/RDS",
        "title": "RDS Connection Timeout Spike",
        "severity": Severity.CRITICAL,
        "description": (
            "RDS instance db-prod-primary exceeded 95% max connection limit. "
            "DatabaseConnections metric at 487/500 for >5 min. "
            "Application returning SQLSTATE 08006 connection_failure."
        ),
        "namespace": "AWS/RDS",
        "metric_value": 487.0,
    },
    {
        "source": "AWS/EC2",
        "title": "EC2 Memory Utilisation Critical",
        "severity": Severity.HIGH,
        "description": (
            "Instance i-0abc123def (c5.2xlarge) memory utilisation at 97.3%. "
            "OOM-killer invoked 4 times in last 10 min. "
            "Process java (PID 8832) consuming 11.2 GiB."
        ),
        "namespace": "CWAgent",
        "metric_value": 97.3,
    },
    {
        "source": "Kubernetes",
        "title": "Pod CrashLoopBackOff — api-server",
        "severity": Severity.CRITICAL,
        "description": (
            "Pod api-server-7f8c6b5d4-xk9zm in namespace production entered "
            "CrashLoopBackOff after 8 restarts. Last exit code 137 (OOMKilled). "
            "Container memory limit: 512Mi, peak usage: 510Mi."
        ),
        "namespace": "production",
        "metric_value": 8.0,
    },
    {
        "source": "AWS/ELB",
        "title": "ALB 5xx Error Rate Surge",
        "severity": Severity.HIGH,
        "description": (
            "Application Load Balancer prod-alb-01 returning HTTP 502/503 at "
            "34% of total requests. Healthy host count dropped from 6 to 2. "
            "Target group arn:aws:...tg-prod-api deregistered 4 targets."
        ),
        "namespace": "AWS/ApplicationELB",
        "metric_value": 34.0,
    },
    {
        "source": "AWS/Lambda",
        "title": "Lambda Throttling — payment-processor",
        "severity": Severity.MEDIUM,
        "description": (
            "Function payment-processor throttled 1,240 invocations in the "
            "last 5 min. Concurrent executions at reserved limit (100). "
            "DLQ depth growing at ~200 msgs/min."
        ),
        "namespace": "AWS/Lambda",
        "metric_value": 1240.0,
    },
    {
        "source": "Kubernetes",
        "title": "Node NotReady — worker-pool-3",
        "severity": Severity.CRITICAL,
        "description": (
            "Node ip-10-0-3-47.ec2.internal transitioned to NotReady. "
            "kubelet stopped posting status 3 min ago. "
            "23 pods need rescheduling. Disk pressure detected prior."
        ),
        "namespace": "kube-system",
        "metric_value": 23.0,
    },
    {
        "source": "AWS/RDS",
        "title": "RDS Replica Lag Exceeded Threshold",
        "severity": Severity.MEDIUM,
        "description": (
            "Read replica db-prod-replica-02 lag reached 48 s (threshold 10 s). "
            "ReplicaLag metric rising steadily. Heavy write workload detected "
            "on primary — WriteIOPS at 12,400."
        ),
        "namespace": "AWS/RDS",
        "metric_value": 48.0,
    },
    {
        "source": "Kubernetes",
        "title": "PersistentVolumeClaim Pending — data-pipeline",
        "severity": Severity.HIGH,
        "description": (
            "PVC data-pipeline-pvc in namespace analytics stuck in Pending "
            "state for 12 min. StorageClass gp3-encrypted has no available PVs. "
            "EBS volume provisioner returning 'VolumeQuotaExceeded'."
        ),
        "namespace": "analytics",
        "metric_value": 12.0,
    },
]

# ── Runbook knowledge to seed cognee's memory ─────────────────────────────
_SEED_RUNBOOKS: list[str] = [
    (
        "INCIDENT RUNBOOK — RDS Connection Timeout\n"
        "Root Cause: Connection pool exhaustion due to long-running queries "
        "holding connections. Often caused by missing indexes on new columns.\n"
        "Resolution: 1) Identify long-running queries via "
        "`SELECT * FROM pg_stat_activity WHERE state='active' ORDER BY "
        "query_start;`  2) Kill idle-in-transaction sessions: "
        "`SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE state='idle in transaction' AND query_start < now()-'5 min'::interval;`  "
        "3) Scale RDS instance if connections are legitimately needed. "
        "4) Tune connection pooler (PgBouncer) max_client_conn.\n"
        "Team: DB-Platform  |  Resolved by: @sarah.chen  |  Date: 2025-11-14\n"
        "Ticket: OPS-4521"
    ),
    (
        "INCIDENT RUNBOOK — EC2 Memory Spike / OOM\n"
        "Root Cause: JVM heap not bounded; default -Xmx caused unbounded "
        "growth during traffic spike.\n"
        "Resolution: 1) SSH to instance and run `sudo dmesg | grep -i oom` to "
        "confirm OOM events.  2) Restart the service: "
        "`sudo systemctl restart api-service`.  "
        "3) Add JVM flag `-Xmx8g` to /etc/sysconfig/api-service.  "
        "4) If recurring, right-size the instance or enable auto-scaling group "
        "policies.\n"
        "Team: Platform-Eng  |  Resolved by: @mike.tanaka  |  Date: 2025-12-02\n"
        "Ticket: OPS-4587"
    ),
    (
        "INCIDENT RUNBOOK — Kubernetes CrashLoopBackOff\n"
        "Root Cause: Container OOMKilled — memory limit too low for workload.\n"
        "Resolution: 1) Check logs: `kubectl logs <pod> --previous`.  "
        "2) Inspect resource usage: "
        "`kubectl top pod -n production`.  "
        "3) Increase memory limit in deployment manifest to 1Gi: "
        "`kubectl set resources deployment/api-server -n production "
        "--limits=memory=1Gi`.  "
        "4) Rolling restart: `kubectl rollout restart deployment/api-server "
        "-n production`.  "
        "5) Verify: `kubectl rollout status deployment/api-server -n production`.\n"
        "Team: K8s-SRE  |  Resolved by: @priya.gupta  |  Date: 2026-01-19\n"
        "Ticket: OPS-4712"
    ),
    (
        "INCIDENT RUNBOOK — ALB 5xx Error Surge\n"
        "Root Cause: Upstream targets failing health checks after a bad deploy.\n"
        "Resolution: 1) Check target group health: "
        "`aws elbv2 describe-target-health --target-group-arn <arn>`.  "
        "2) Rollback deployment: `kubectl rollout undo deployment/api-server "
        "-n production`.  "
        "3) If targets are EC2, verify security group allows health check port.  "
        "4) Re-register healthy targets and monitor 2xx rate recovery.\n"
        "Team: Platform-Eng  |  Resolved by: @carlos.reyes  |  Date: 2026-02-07\n"
        "Ticket: OPS-4801"
    ),
    (
        "INCIDENT RUNBOOK — Lambda Throttling\n"
        "Root Cause: Reserved concurrency limit reached during flash sale event.\n"
        "Resolution: 1) Increase reserved concurrency: "
        "`aws lambda put-function-concurrency --function-name payment-processor "
        "--reserved-concurrent-executions 500`.  "
        "2) Reprocess DLQ messages: "
        "`aws sqs receive-message --queue-url <dlq-url> --max-number-of-messages 10`.  "
        "3) Enable provisioned concurrency for predictable latency.  "
        "4) Implement exponential back-off in upstream callers.\n"
        "Team: Serverless-Eng  |  Resolved by: @aisha.okafor  |  Date: 2026-03-11\n"
        "Ticket: OPS-4899"
    ),
    (
        "INCIDENT RUNBOOK — Kubernetes Node NotReady\n"
        "Root Cause: Disk pressure caused kubelet to stop — /var/lib/docker "
        "filled by orphaned container images.\n"
        "Resolution: 1) Cordon the node: `kubectl cordon <node>`.  "
        "2) Drain workloads: `kubectl drain <node> --ignore-daemonsets "
        "--delete-emptydir-data`.  "
        "3) SSH and clean up: `docker system prune -af && journalctl --vacuum-size=500M`.  "
        "4) Uncordon when healthy: `kubectl uncordon <node>`.  "
        "5) Add disk monitoring alert at 80% threshold.\n"
        "Team: K8s-SRE  |  Resolved by: @priya.gupta  |  Date: 2026-04-22\n"
        "Ticket: OPS-4955"
    ),
    (
        "INCIDENT RUNBOOK — RDS Replica Lag\n"
        "Root Cause: Heavy write workload on primary saturating I/O; replica "
        "cannot keep up with WAL replay.\n"
        "Resolution: 1) Check write IOPS: `aws cloudwatch get-metric-statistics "
        "--namespace AWS/RDS --metric-name WriteIOPS ...`.  "
        "2) Temporarily redirect reads to primary.  "
        "3) Scale replica to a larger instance class with higher I/O capacity.  "
        "4) Evaluate write batching and reduce transaction frequency.\n"
        "Team: DB-Platform  |  Resolved by: @sarah.chen  |  Date: 2026-05-08\n"
        "Ticket: OPS-5010"
    ),
    (
        "INCIDENT RUNBOOK — PVC Pending (EBS Quota)\n"
        "Root Cause: AWS EBS volume quota exceeded in the AZ.\n"
        "Resolution: 1) Check quota: `aws service-quotas get-service-quota "
        "--service-code ebs --quota-code L-D18FCD1D`.  "
        "2) Request quota increase via AWS console or CLI.  "
        "3) Alternatively, delete unused EBS volumes: "
        "`aws ec2 describe-volumes --filters Name=status,Values=available`.  "
        "4) Re-trigger PVC binding: `kubectl delete pvc <name> && kubectl apply -f pvc.yaml`.\n"
        "Team: Platform-Eng  |  Resolved by: @carlos.reyes  |  Date: 2026-06-01\n"
        "Ticket: OPS-5078"
    ),
]


def generate_alert() -> DevOpsAlert:
    """Return a randomly selected simulated DevOps alert."""
    template = random.choice(_ALERT_TEMPLATES)
    return DevOpsAlert(
        source=template["source"],
        title=template["title"],
        severity=template["severity"],
        description=template["description"],
        namespace=template["namespace"],
        metric_value=template.get("metric_value"),
        region=random.choice(["us-east-1", "us-west-2", "eu-west-1"]),
    )


# ═══════════════════════════════════════════════════════════════════════════
#  §2  DISPLAY HELPERS  (Rich console output)
# ═══════════════════════════════════════════════════════════════════════════

_SEV_COLORS = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "bold yellow",
    Severity.MEDIUM: "bold cyan",
    Severity.LOW: "dim white",
}


def _render_alert(alert: DevOpsAlert) -> Panel:
    """Build a rich Panel that looks like a PagerDuty card."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold white", min_width=14)
    table.add_column()
    table.add_row("Alert ID", alert.alert_id)
    table.add_row("Timestamp", alert.timestamp)
    table.add_row("Source", alert.source)
    table.add_row("Namespace", alert.namespace)
    table.add_row("Region", alert.region)
    sev_text = Text(alert.severity.value, style=_SEV_COLORS[alert.severity])
    table.add_row("Severity", sev_text)
    if alert.metric_value is not None:
        table.add_row("Metric", str(alert.metric_value))
    table.add_row("Description", alert.description)
    return Panel(
        table,
        title=f"🚨  {alert.title}",
        border_style=_SEV_COLORS[alert.severity],
        box=box.HEAVY,
    )


def _section(icon: str, title: str) -> None:
    console.print()
    console.rule(f"  {icon}  {title}  ", style="bright_blue")
    console.print()


# ═══════════════════════════════════════════════════════════════════════════
#  §3  COGNEE PIPELINE OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════


async def seed_knowledge_base() -> None:
    """
    One-time bootstrap: load historical incident runbooks into cognee so the
    very first alert already has context to recall.
    """
    _section("📚", "SEEDING KNOWLEDGE BASE WITH HISTORICAL RUNBOOKS")
    console.print(
        f"[dim]Ingesting {len(_SEED_RUNBOOKS)} runbook(s) into cognee memory…[/dim]"
    )

    for idx, runbook in enumerate(_SEED_RUNBOOKS, 1):
        console.print(f"  [dim]  • Runbook {idx}/{len(_SEED_RUNBOOKS)}…[/dim]")
        # remember() → ingests, extracts entities, builds graph, indexes vectors
        await cognee.remember(runbook)

    console.print("[bold green]✓ Knowledge base seeded successfully.[/bold green]")


async def recall_past_resolutions(alert: DevOpsAlert) -> str:
    """
    §3-A  "Never-Forget" Recall
    Query cognee for prior incidents matching this alert pattern.
    """
    _section("🔍", "QUERYING MEMORY — NEVER-FORGET RECALL")

    query = (
        f"Have we seen this exact error pattern before? "
        f"Alert source: {alert.source}. "
        f"Issue: {alert.title}. "
        f"Details: {alert.description}. "
        f"Who fixed it last time, and what was the resolution script or "
        f"kubectl command?"
    )
    console.print(f"[dim]Query → {query[:120]}…[/dim]\n")

    results = await cognee.recall(query)

    if not results:
        console.print("[yellow]⚠  No prior resolutions found in memory.[/yellow]")
        return ""

    # Collect recall output into a single context string
    context_parts: list[str] = []
    for i, result in enumerate(results, 1):
        # cognee recall results expose their content via various attrs;
        # normalise gracefully.
        text = (
            getattr(result, "text", None)
            or getattr(result, "content", None)
            or getattr(result, "payload", None)
            or str(result)
        )
        context_parts.append(text)
        console.print(
            Panel(
                str(text)[:600],
                title=f"Memory Hit #{i}",
                border_style="green",
                box=box.ROUNDED,
            )
        )

    context = "\n---\n".join(context_parts)
    console.print(f"\n[bold green]✓ Retrieved {len(results)} memory hit(s).[/bold green]")
    return context


def automated_triage(alert: DevOpsAlert, recall_context: str) -> str:
    """
    §3-B  Automated Triage (mock execution).
    Deterministically pick a remediation action based on alert source + title.
    In production this would call a real runbook executor.
    """
    _section("⚡", "AUTOMATED TRIAGE — MOCK EXECUTION")

    # ── Remediation lookup ─────────────────────────────────────────────────
    _REMEDIATIONS: dict[str, dict] = {
        "RDS Connection Timeout Spike": {
            "team": "DB-Platform",
            "action": (
                "Executing: SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE state='idle in transaction' AND query_start < "
                "now()-'5 min'::interval;"
            ),
            "ticket_prefix": "DB",
        },
        "EC2 Memory Utilisation Critical": {
            "team": "Platform-Eng",
            "action": (
                "Executing: sudo systemctl restart api-service && "
                "sudo sed -i 's/-Xmx[^ ]*/-Xmx8g/' /etc/sysconfig/api-service"
            ),
            "ticket_prefix": "PLAT",
        },
        "Pod CrashLoopBackOff — api-server": {
            "team": "K8s-SRE",
            "action": (
                "Executing: kubectl set resources deployment/api-server "
                "-n production --limits=memory=1Gi && "
                "kubectl rollout restart deployment/api-server -n production"
            ),
            "ticket_prefix": "K8S",
        },
        "ALB 5xx Error Rate Surge": {
            "team": "Platform-Eng",
            "action": (
                "Executing: kubectl rollout undo deployment/api-server "
                "-n production  (rollback to last known-good revision)"
            ),
            "ticket_prefix": "PLAT",
        },
        "Lambda Throttling — payment-processor": {
            "team": "Serverless-Eng",
            "action": (
                "Executing: aws lambda put-function-concurrency "
                "--function-name payment-processor "
                "--reserved-concurrent-executions 500"
            ),
            "ticket_prefix": "SLS",
        },
        "Node NotReady — worker-pool-3": {
            "team": "K8s-SRE",
            "action": (
                "Executing: kubectl cordon ip-10-0-3-47.ec2.internal && "
                "kubectl drain ip-10-0-3-47.ec2.internal --ignore-daemonsets "
                "--delete-emptydir-data"
            ),
            "ticket_prefix": "K8S",
        },
        "RDS Replica Lag Exceeded Threshold": {
            "team": "DB-Platform",
            "action": (
                "Executing: aws rds modify-db-instance "
                "--db-instance-identifier db-prod-replica-02 "
                "--db-instance-class db.r6g.2xlarge --apply-immediately"
            ),
            "ticket_prefix": "DB",
        },
        "PersistentVolumeClaim Pending — data-pipeline": {
            "team": "Platform-Eng",
            "action": (
                "Executing: aws service-quotas request-service-quota-increase "
                "--service-code ebs --quota-code L-D18FCD1D --desired-value 200"
            ),
            "ticket_prefix": "PLAT",
        },
    }

    remediation = _REMEDIATIONS.get(alert.title)

    if remediation:
        ticket_id = f"{remediation['ticket_prefix']}-{random.randint(5100, 5999)}"
        team = remediation["team"]
        action = remediation["action"]
    else:
        # Fallback for unknown alert types
        ticket_id = f"GEN-{random.randint(9000, 9999)}"
        team = "On-Call SRE"
        action = (
            "No matching runbook found. Escalating to on-call engineer. "
            "Assigning ticket for manual investigation."
        )

    # ── Display triage result ──────────────────────────────────────────────
    triage_table = Table(
        title="Triage Decision",
        box=box.DOUBLE_EDGE,
        border_style="bright_magenta",
        show_lines=True,
    )
    triage_table.add_column("Field", style="bold", min_width=16)
    triage_table.add_column("Value")
    triage_table.add_row("Assigned Team", f"[bold]{team}[/bold]")
    triage_table.add_row("Ticket", ticket_id)
    triage_table.add_row("Severity", Text(alert.severity.value, style=_SEV_COLORS[alert.severity]))
    triage_table.add_row("Automated Action", f"[bold cyan]{action}[/bold cyan]")
    has_context = "Yes — matched prior incidents" if recall_context else "No — first occurrence"
    triage_table.add_row("Memory Context", has_context)
    console.print(triage_table)

    resolution_summary = (
        f"Alert '{alert.title}' triaged to {team} (ticket {ticket_id}). "
        f"Action taken: {action}"
    )
    return resolution_summary


async def learning_loop(alert: DevOpsAlert, resolution_summary: str) -> None:
    """
    §3-C  The Learning Loop
    Simulate a human confirming the fix, then write the enriched resolution
    back into cognee's knowledge graph so future recalls are richer.
    """
    _section("🧠", "LEARNING LOOP — ENRICHING MEMORY")

    # Simulate human confirmation
    human_confirmation = random.choice(
        [
            "Confirmed: fix applied successfully. Service recovered within 2 min.",
            "Confirmed: automated remediation resolved the issue. No customer impact.",
            "Confirmed with modification: initial fix worked but we also applied "
            "a config patch to prevent recurrence.",
            "Confirmed: rollback completed. Monitoring shows metrics back to normal.",
        ]
    )
    console.print(
        Panel(
            f"[bold green]{human_confirmation}[/bold green]",
            title="👤 Human Confirmation (Simulated)",
            border_style="green",
        )
    )

    # Build an enriched knowledge document
    enriched_doc = (
        f"RESOLVED INCIDENT — {alert.title}\n"
        f"Alert ID: {alert.alert_id}\n"
        f"Source: {alert.source} | Region: {alert.region}\n"
        f"Severity: {alert.severity.value}\n"
        f"Description: {alert.description}\n"
        f"Triage Summary: {resolution_summary}\n"
        f"Human Confirmation: {human_confirmation}\n"
        f"Resolved At: {datetime.now(timezone.utc).isoformat()}\n"
        f"Learning: This resolution pattern should be auto-applied for "
        f"matching future alerts from {alert.source}."
    )

    console.print("[dim]Writing enriched resolution back into cognee memory…[/dim]")

    # remember() persists the new knowledge into graph + vector stores
    await cognee.remember(enriched_doc)

    # improve() triggers background enrichment — bridging session data into
    # permanent memory and refining retrieval structures
    try:
        await cognee.improve()
        console.print(
            "[bold green]✓ Memory improved — graph enrichment pass complete.[/bold green]"
        )
    except Exception as exc:
        # improve() may not be available in all cognee versions; fall back
        console.print(
            f"[yellow]⚠  cognee.improve() skipped ({exc}). "
            f"Data was still persisted via remember().[/yellow]"
        )

    console.print(
        "[bold green]✓ Learning loop complete — future recalls will include "
        "this resolution.[/bold green]"
    )


# ═══════════════════════════════════════════════════════════════════════════
#  §4  MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════


async def run_pipeline(num_alerts: int = 3, seed: bool = True) -> None:
    """
    End-to-end SRE Commander pipeline.

    Args:
        num_alerts: How many simulated alerts to process.
        seed:       Whether to seed the knowledge base on first run.
    """
    # ── Banner ─────────────────────────────────────────────────────────────
    console.print(
        Panel(
            "[bold bright_white]AI SRE COMMANDER[/bold bright_white]\n"
            "[dim]The Self-Healing DevOps Pipeline — powered by Cognee + Ollama[/dim]",
            border_style="bright_blue",
            box=box.DOUBLE,
            padding=(1, 4),
        )
    )

    # ── Step 0: Seed historical knowledge ──────────────────────────────────
    if seed:
        await seed_knowledge_base()

    # ── Process N alerts ───────────────────────────────────────────────────
    for cycle in range(1, num_alerts + 1):
        console.print()
        console.rule(
            f"  🔄  ALERT CYCLE {cycle} / {num_alerts}  ",
            style="bold bright_white",
        )

        # Step 1 — Ingest a mock alert
        _section("📥", "STEP 1 · MOCK ALERT INGESTION")
        alert = generate_alert()
        console.print(_render_alert(alert))

        # Step 2 — Recall past resolutions
        recall_context = await recall_past_resolutions(alert)

        # Step 3 — Automated triage (mock)
        resolution_summary = automated_triage(alert, recall_context)

        # Step 4 — Learning loop (persist enriched resolution)
        await learning_loop(alert, resolution_summary)

    # ── Summary ────────────────────────────────────────────────────────────
    console.print()
    console.print(
        Panel(
            f"[bold green]Pipeline complete.[/bold green] "
            f"Processed {num_alerts} alert(s).\n"
            f"[dim]The knowledge graph now contains {num_alerts} additional "
            f"enriched resolution(s) for future triage.[/dim]",
            title="✅  SRE COMMANDER — RUN COMPLETE",
            border_style="bold green",
            box=box.DOUBLE,
            padding=(1, 2),
        )
    )


# ═══════════════════════════════════════════════════════════════════════════
#  §5  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════


def main() -> None:
    """CLI entry point — parses a simple flag and launches the async pipeline."""
    import argparse

    parser = argparse.ArgumentParser(
        description="AI SRE Commander — The Self-Healing DevOps Pipeline"
    )
    parser.add_argument(
        "-n",
        "--num-alerts",
        type=int,
        default=3,
        help="Number of simulated alerts to process (default: 3)",
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Skip seeding the knowledge base (use if already seeded)",
    )
    args = parser.parse_args()

    asyncio.run(run_pipeline(num_alerts=args.num_alerts, seed=not args.no_seed))


if __name__ == "__main__":
    main()
