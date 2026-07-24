# Scaling to 10,000+ customers/day

How this POC scales from 20 synthetic customers to production volume, and the infrastructure to run it.

## The key insight: separate the cheap layer from the expensive layer

Not every customer needs an LLM. The two layers have wildly different costs:

| Layer | Cost per customer | 10k/day |
|-------|-------------------|---------|
| **Deterministic rules** (`rules.py`) | ~0.6 ms | **~6 seconds total** |
| **Multi-step LLM graph** (`orchestrator.py`) | ~60 s, 5 model calls | 10k × 60s = **infeasible if run on everyone** |

Measured: `python src/pipeline.py` → rules score **20,000 customers in ~12s ≈ 1,700/sec ≈ 147M/day per core**. The deterministic layer is effectively free at this scale. The LLM is the only thing that costs real money and latency — so we **gate** it.

## Lever 1 — Gating (`crosscheck_policy: "gated"`)

Rules score 100% of the population. The LLM only runs where it changes the decision:

- **LOW band** → rules-decisive → **auto-clear** (no LLM).
- **HIGH band / kill-switch** → rules-decisive → **escalate** (no LLM).
- **MED band** (the uncertain middle) → **run the multi-step LLM graph** for a second opinion.

In a realistic population only ~10–20% land in the ambiguous middle, so the LLM touches **~1–2k of 10k**, not all 10k. Set in `config.py → scale.crosscheck_policy`.

## Lever 2 — Parallelism (`pipeline.py`)

LLM calls are I/O-bound, so a `ThreadPoolExecutor` overlaps them. 1,500 gated customers × 60s ÷ 32 workers ≈ **~45 min** of wall-clock — run as an async batch, not on the request path. Concurrency is capped (`scale.workers`) to respect provider rate limits, with retry+backoff per call.

## Lever 3 — Caching (`data/llm_cache.json` → Redis in prod)

Every LLM finding is cached by `provider:model:prompt_hash`. A customer whose signals haven't changed is **never re-scored by the LLM**. Re-runs are instant. In production this becomes a Redis/Memcached layer keyed by the customer's input fingerprint (already computed: `AuditRecord.input_fingerprint`).

## Lever 4 — Precomputed read store (`store.py`)

The dashboard must never re-score on page load. Workers write decisions to an indexed **SQLite** table (`decisions`, indexed on band/action/score); the UI and any API read from it. Swap SQLite → **Postgres** by changing only `store.py` — the interface (`upsert_many` / `query` / `get`) is stable.

## Production architecture (10k–1M/day)

```
                      ┌──────────────┐
  ingest (CSV/JSON/   │  ingestion   │  batch or streaming; normalise -> Dossier (pydantic-validated)
  Kafka/S3/webhook) ─►│   service    │
                      └──────┬───────┘
                             ▼
                      ┌──────────────┐   durable queue (SQS / Kafka / Redis Streams)
                      │  work queue  │   one message per customer, at-least-once
                      └──────┬───────┘
                             ▼   (N autoscaled workers)
        ┌────────────────────────────────────────────┐
        │  worker: rules.score_customer  (always)     │
        │          gate -> MED? run LangGraph graph   │   ← rate-limited, cached, retried
        │          reconcile -> route -> AuditRecord  │
        └───────┬──────────────────────────┬──────────┘
                ▼                           ▼
      ┌──────────────────┐        ┌───────────────────┐
      │ decisions store  │        │  append-only audit │  (immutable; regulator-facing)
      │ (Postgres)       │        │  (Postgres/S3)     │
      └────────┬─────────┘        └───────────────────┘
               ▼
      ┌──────────────────┐        ┌───────────────────┐
      │ dashboard / API  │◄───────│  LangSmith         │  traces every graph run (opt-in)
      │ (reads store)    │        │  (observability)   │
      └──────────────────┘        └───────────────────┘
```

**Mapping to what's already built** — every box has a working local stand-in:

| Production | This repo |
|------------|-----------|
| Ingestion service | `models.load_dossiers` / Decimal-safe loader (accepts CSV/JSON) |
| Work queue + workers | `pipeline.assess_all_scaled` (ThreadPoolExecutor; swap for Celery/Kafka consumers) |
| Rules + gate + graph | `rules.py`, `pipeline.should_crosscheck`, `orchestrator.py` |
| LLM cache | `data/llm_cache.json` (→ Redis) |
| Decisions store | `store.py` SQLite (→ Postgres) |
| Audit log | `audit.py` JSONL (→ Postgres/S3, WORM) |
| Observability | LangSmith `@traceable` on the graph (opt-in) |

## What changes at each scale

- **10k/day** — a single box handles it. Rules in seconds; ~1–2k gated LLM calls over the day; SQLite is fine.
- **100k/day** — move the queue to SQS/Kafka, workers to a container autoscaler, cache to Redis, store to Postgres.
- **1M+/day** — shard workers by region, add a cheaper/faster model for the gated tier (or a distilled classifier for the MED band), pre-batch LLM calls, and tier the audit store to object storage.

## Cost & latency controls (config knobs)

- `scale.crosscheck_policy` — `all` (quality) vs `gated` (cost).
- `scale.workers` — parallelism vs provider rate limits.
- `llm.multi_step` — 5-call graph (robust) vs single call (cheap/fast).
- `llm.provider` / model — swap to a faster/cheaper model for the gated tier without touching logic.
- Cache TTL / fingerprint — re-score only when a customer's inputs actually change.

## Observability (LangSmith)

Set `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY` and every `crosscheck` (and each LangGraph node) streams to LangSmith — inputs, per-node latency, token usage, errors, and the full graph trace. No code change; the `@traceable` wrapper is a no-op when disabled. This is how you debug a bad score in production: open the trace, see which domain analyst or the verifier went wrong.
