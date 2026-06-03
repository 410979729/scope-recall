# External shared-memory integration contract

`scope-recall` is a local-first Hermes memory provider. It is designed to run inside each Hermes profile as the per-agent recall layer, not as a distributed cluster memory authority.

If your deployment already has a shared center such as PostgreSQL, Redis-backed knowledge services, or another multi-agent memory backend, keep that system as the cross-agent source of truth and bridge to `scope-recall` deliberately.

## Responsibilities

### External shared backend owns

- cross-agent source of truth
- global knowledge synchronization
- permissions and tenancy
- cluster-scale conflict policy
- PostgreSQL-scale indexing, audit, and retention
- fan-out/fan-in across many Hermes instances

### `scope-recall` owns

- current-turn recall for one Hermes runtime
- local SQLite truth rows for provider-owned memory
- LanceDB companion retrieval index
- local scratch isolation
- per-user/per-agent durable recall
- scoped import/export/tool surfaces
- doctor, repair, inspect, explain, and benchmark utilities

## Safe synchronization targets

External bridge code may choose to synchronize durable rows with these targets:

```text
user
memory
project
ops
```

Do not synchronize these by default:

```text
general
raw system output
raw tool output
secret-like records
temporary chat/thread scratch
```

`general` is local scratch. It should remain inside the current runtime scope unless an operator deliberately promotes a sanitized item into a durable target.

## Recommended modes

### Read-only bridge

Use this when a central backend should inform a Hermes instance without letting local recall mutate global truth automatically.

1. External backend selects durable facts for one user/agent/workspace.
2. Bridge writes sanitized rows with `scope_recall_store` or imports them into SQLite truth.
3. `scope-recall` recalls them locally for the current query.
4. Local updates are reviewed before being sent back to the external backend.

### Writeback bridge

Use this only when the external backend has a clear conflict policy.

1. Local agent writes durable `user`/`memory`/`project`/`ops` rows.
2. Bridge exports only durable rows, never `general` scratch.
3. External backend resolves duplicates/conflicts.
4. Accepted central facts are written back or re-imported with source/trust metadata.

## Conflict policy hooks

Bridge code should decide and document at least one policy:

- central backend wins
- curated user memory wins
- newest durable fact wins
- highest source-trust row wins
- user-confirmed rows supersede agent/tool-derived rows
- conflicts are only marked, never auto-deleted

`scope-recall` can expose evidence through `scope_recall_inspect`, `scope_recall_explain`, `memory_relations`, and `memory_feedback`, but it should not become the global conflict resolver.

## Source trust guidance

Recommended source ordering for cross-system imports:

1. explicit user-confirmed central records
2. Hermes curated memory (`USER.md` / `MEMORY.md`) when allowlisted
3. operator-reviewed `scope-recall` durable rows
4. tool-derived facts with sanitized evidence
5. raw assistant inference

Bridge metadata should preserve provenance whenever possible:

```json
{
  "source_system": "central-postgres",
  "source_trust": 0.9,
  "import_mode": "read_only",
  "external_record_id": "..."
}
```

## Minimal JSONL shape

A bridge-friendly export/import row should include:

```json
{
  "id": "local-or-external-id",
  "target": "project",
  "content": "SQLite remains the truth layer for scope-recall; LanceDB is rebuildable.",
  "summary": "scope-recall truth/vector boundary",
  "memory_type": "project",
  "entities": ["scope-recall", "SQLite", "LanceDB"],
  "tags": ["memory-architecture"],
  "source": "operator-reviewed",
  "updated_at": "2026-06-03T00:00:00Z",
  "metadata": {
    "source_system": "central-postgres",
    "source_trust": 0.9
  }
}
```

## Non-goals

`scope-recall` does not implement these as built-in core features:

- Tailscale + SQLite replication
- Redis pub/sub memory propagation
- cross-instance durable scope auto-sync
- cluster-wide permissions or tenant governance
- automatic Hermes skill creation
- full holographic memory graph parity
- always-on LLM governance classifier by default

For clusters, keep the shared center outside `scope-recall`; use `scope-recall` as the local recall/cache/tooling layer with explicit boundaries.
