# 🚨 AI SRE Commander — The Self-Healing DevOps Pipeline

> An asynchronous Python workflow that ingests simulated DevOps alerts, queries a persistent hybrid **graph + vector** memory via [Cognee](https://github.com/topoteretes/cognee) to find past resolutions, simulates automated remediation, and learns from each outcome, all running **100% locally** with zero cloud API dependencies.

---

## Architecture

```
┌──────────────┐   ┌─────────────┐   ┌──────────────┐
│   Qdrant     │   │   Neo4j     │   │   Ollama     │
│ (vectors)    │◄──┤  (graph)    │   │  (local LLM) │
│ :6333        │   │  :7687      │   │  :11434      │
└──────┬───────┘   └──────┬──────┘   └──────┬───────┘
       │                  │                  │
       └──────────┬───────┘──────────────────┘
                  │
          ┌───────▼────────┐
          │     Cognee     │
          │  (hybrid RAG   │
          │   memory layer)│
          └───────┬────────┘
                  │
       ┌──────────▼──────────┐
       │  sre_commander.py   │
       │                     │
       │ 1. Ingest Alert     │
       │ 2. Recall Memory    │
       │ 3. Auto-Triage      │
       │ 4. Learn & Improve  │
       └─────────────────────┘
```

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| [Docker](https://docs.docker.com/get-docker/) & Docker Compose | 24+ | Runs Qdrant, Neo4j, Ollama |
| [Python](https://python.org) | 3.11+ | Runs the pipeline script |
| [Ollama](https://ollama.com) *(optional host install)* | Latest | Can also run natively on the host |

---

## Quick Start

### 1. Clone & enter the project

```bash
cd "The Hangover Part AI"
```

### 2. Start local infrastructure

```bash
docker compose up -d
```

This launches three containers:

| Service | Port(s) | UI |
|---------|---------|-----|
| **Qdrant** | `6333` (REST), `6334` (gRPC) | http://localhost:6333/dashboard |
| **Neo4j** | `7474` (browser), `7687` (Bolt) | http://localhost:7474 |
| **Ollama** | `11434` | — |

### 3. Pull the local LLM models

```bash
# Chat / reasoning model
docker exec sre-ollama ollama pull llama3.1:8b

# Embedding model
docker exec sre-ollama ollama pull nomic-embed-text
```

> **Tip:** If you already have Ollama installed on your host, you can `ollama pull` directly and skip the Docker Ollama container. Just make sure `LLM_ENDPOINT` in `.env` points to the right address.

### 4. Create a Python virtual environment & install dependencies

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 5. Configure environment variables

The `.env` file is already pre-configured to connect to the Docker services. Review and adjust if needed:

```env
LLM_PROVIDER=ollama
LLM_MODEL=llama3.1:8b
LLM_ENDPOINT=http://localhost:11434
LLM_API_KEY=ollama

EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSIONS=768

VECTOR_DB_PROVIDER=qdrant
VECTOR_DB_URL=http://localhost:6333

GRAPH_DATABASE_PROVIDER=neo4j
GRAPH_DATABASE_URL=bolt://localhost:7687
GRAPH_DATABASE_NAME=neo4j
GRAPH_DATABASE_USERNAME=neo4j
GRAPH_DATABASE_PASSWORD=sre_commander_pass
```

### 6. Run the SRE Commander

```bash
python sre_commander.py
```

**CLI options:**

```
python sre_commander.py --help

  -n, --num-alerts N   Number of alerts to process (default: 3)
  --no-seed            Skip seeding the knowledge base (if already seeded)
```

**Example — process 5 alerts without re-seeding:**

```bash
python sre_commander.py -n 5 --no-seed
```

---

## How It Works

The pipeline executes four steps for each alert cycle:

### Step 1 · Mock Alert Ingestion
Generates a realistic DevOps alert from a catalogue of **8 templates** covering:
- RDS connection timeouts & replica lag
- EC2 memory spikes (OOMKilled)
- Kubernetes CrashLoopBackOff & Node NotReady
- ALB 5xx error surges
- Lambda throttling
- PVC pending (EBS quota)

### Step 2 · "Never-Forget" Recall
Calls `await cognee.recall(query)` with a natural-language question that includes the alert's source, title, and description. Cognee automatically routes the query through both **vector similarity search** and **graph traversal** to find matching past incidents.

### Step 3 · Automated Triage (Mock Execution)
Maps the alert to a deterministic remediation action — the kind of `kubectl`, `aws`, or SQL command an SRE would run. Displays a rich terminal card with the assigned team, ticket ID, and executed command.

### Step 4 · Learning Loop
1. Simulates a **human confirmation** of the fix.
2. Builds an enriched resolution document combining the original alert, triage action, and human feedback.
3. Calls `await cognee.remember(enriched_doc)` to persist the resolution into both the vector and graph stores.
4. Calls `await cognee.improve()` to trigger a background enrichment pass that refines the knowledge graph.

Each cycle makes future recalls **richer and more accurate** — the system literally learns from every incident it processes.

---

## Seed Data

On first run (unless `--no-seed` is passed), the pipeline ingests **8 historical incident runbooks** into Cognee's memory. These cover real-world patterns like:

- Connection pool exhaustion on RDS
- JVM heap unbounded growth
- Container OOMKill in Kubernetes
- Bad deployment causing ALB 5xx
- Lambda concurrency limits
- Kubelet disk pressure
- Replica lag from write saturation
- EBS volume quota exceeded

This gives the "Never-Forget" recall system immediate context from day one.

---

## Inspecting the Knowledge Graph

After running the pipeline, open the **Neo4j Browser** at [http://localhost:7474](http://localhost:7474) and run:

```cypher
MATCH (n) RETURN n LIMIT 100
```

You'll see the entities and relationships that Cognee extracted from your runbooks and resolved incidents.

---

## Teardown

```bash
# Stop and remove containers (data persists in volumes)
docker compose down

# Stop and remove containers AND delete all data
docker compose down -v
```

---

## Project Structure

```
The Hangover Part AI/
├── .env                  # Environment configuration (local services)
├── docker-compose.yml    # Qdrant + Neo4j + Ollama infrastructure
├── requirements.txt      # Python dependencies
├── sre_commander.py      # Core pipeline logic
└── README.md             # This file
```

---

## License

This is a prototype / educational project. Use it as a starting point for building production-grade AI-augmented SRE workflows.
