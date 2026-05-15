# scope-recall

<div align="center">

**Hermes current-turn memory provider with SQLite truth storage and a LanceDB vector companion**

Current-turn recall · SQLite truth · LanceDB companion · Hybrid retrieval · Strong scope isolation · Deterministic governance

[![CI](https://github.com/joyjoy-ai/scope-recall/actions/workflows/ci.yml/badge.svg)](https://github.com/joyjoy-ai/scope-recall/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Hermes Plugin](https://img.shields.io/badge/Hermes-Memory%20Provider-blue)](https://hermes-agent.nousresearch.com/docs)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](pyproject.toml)

</div>

`scope-recall` is a Hermes local memory provider built for **current-turn recall** with strong runtime scope isolation.

Version `1.0.0` is the first stable V1 release line. The V1 compatibility contract is documented in [`docs/stability.md`](docs/stability.md).

It uses a **two-layer design**:

- **SQLite truth store** for durable local records and deterministic auditing
- **LanceDB vector companion** for semantic retrieval and hybrid ranking

This replaces the old `lancepro` naming, which was misleading because the earlier implementation was SQLite-only.

## Why this provider?

Hermes already has curated durable memory files, and gateway deployments often run across multiple chats, groups, topics, users, and agent identities. A memory provider for that environment must avoid stale context bleed and must make storage ownership obvious.

`scope-recall` focuses on that exact problem:

| Concern | `scope-recall` V1 answer |
| --- | --- |
| Truth storage | SQLite is authoritative; LanceDB is rebuildable companion state |
| Recall timing | `prefetch(query)` recalls for the current turn; `queue_prefetch()` is intentionally a no-op |
| Scope isolation | agent workspace + identity + platform + user + chat/session + thread |
| Offline bootstrap | local deterministic fallback embedder works without API keys |
| Higher-quality retrieval | OpenAI-compatible Gemini embedding default when credentials exist |
| Governance | deterministic dedupe, filtering, metadata classification, and decay review |
| Migration | legacy local `lancepro` auto-migration; OpenClaw import is explicit |

## What it does

- recalls against the **current user query** inside `prefetch()`
- keeps `queue_prefetch()` as a no-op to avoid stale next-turn injection
- reads Hermes built-in curated memory files live at recall time
- stores provider-owned captures in a local SQLite database
- optionally ranks SQLite candidates with a LanceDB companion vector index
- audits and repairs the vector companion by stable SQLite row id during normal sync

## Installation assumption for Hermes users

This project is published for people who want to **download it and use it with Hermes**.

The intended install shape today is:

1. download or clone this plugin directory
2. place the unpacked directory at `$HERMES_HOME/plugins/scope-recall/`
3. enable it in Hermes as a local plugin / memory provider

Important boundary:

- current Hermes plugin discovery expects an **unpacked plugin directory**
- a wheel build is useful for packaging/release verification, but it is **not** the primary install path for Hermes users yet
- do not read wheel build success as proof that Hermes can install or discover the plugin directly from the wheel alone

## Quick start

```bash
cd "$HERMES_HOME/plugins"
git clone https://github.com/joyjoy-ai/scope-recall.git scope-recall
cd scope-recall
python -m pip install -e .
```

Then configure Hermes to use the provider name:

```yaml
memory:
  provider: scope-recall
```

For a local smoke check after installation:

```bash
hermes memory status
```

## Configuration

The shipped `config.json` defaults to hybrid retrieval with a hosted OpenAI-compatible Gemini embedding path and a deterministic offline fallback.

Minimal default shape:

```json
{
  "retrieval": {
    "mode": "hybrid",
    "lexical_weight": 0.45,
    "vector_weight": 0.55
  },
  "vector": {
    "enabled": true,
    "backend": "lancedb",
    "embedder": {
      "provider": "openai-compatible",
      "model": "gemini-embedding-001",
      "dimensions": 3072,
      "api_key_env": ["OPENAI_API_KEY", "GOOGLE_API_KEY"],
      "base_url": "https://generativelanguage.googleapis.com/v1beta/openai"
    },
    "fallback_embedder": {
      "provider": "local-hash",
      "dimensions": 256,
      "model": "hash-v1"
    }
  }
}
```

Credential rule:

- put real API keys in your private environment, not in `config.json`
- if no configured key is available, `scope-recall` falls back to `local-hash`

## Storage layout

Under the active Hermes profile:

- `$HERMES_HOME/scope-recall/memory.sqlite3`
- `$HERMES_HOME/scope-recall/config.json`
- `$HERMES_HOME/scope-recall/lancedb/`

Legacy `lancepro` storage is migrated forward on first initialization when present.

## Architecture

```text
Hermes turn
   |
   | current query
   v
prefetch(query)
   |
   +--> live curated memory read
   |       - $HERMES_HOME/memories/USER.md
   |       - $HERMES_HOME/memories/MEMORY.md
   |
   +--> SQLite truth lookup / FTS
   |       - provider-owned memory rows
   |       - scope metadata
   |       - timestamps and governance metadata
   |
   +--> LanceDB vector companion
   |       - semantic candidate retrieval
   |       - rebuildable from SQLite truth
   |
   v
hybrid scoring + recency-aware ranking + bounded prompt block
```

### 1. SQLite truth layer

SQLite is the authoritative provider-owned store.

It keeps:

- raw memory rows
- scope metadata
- lexical FTS index
- timestamps for auditing and migration

Why SQLite stays authoritative:

- deterministic local persistence
- easy schema inspection
- simple migration/backup story
- safer open-source baseline than tying truth directly to a vector backend

### 2. LanceDB vector companion

LanceDB is a **companion retrieval index**, not the truth source.

It stores:

- `id`
- `scope_id`
- `source`
- `target`
- `content`
- `summary`
- `updated_at`
- `vector`

Configured default embedder targets the Gemini OpenAI-compatible embeddings API:

- `provider: openai-compatible`
- `model: gemini-embedding-001`
- `dimensions: 3072`

Runtime fallback remains available:

- if the configured API embedder is unavailable, the plugin falls back to `local-hash` (`256` dims)
- this keeps first-boot/local operation working even without external API keys, while preserving a higher-quality default config for instances that do provide credentials

## Vector repair and stats

SQLite is the cardinality authority. During vector sync, the provider compares SQLite ids with LanceDB ids, deletes stale vector rows, collapses duplicate physical rows by id, and embeds missing/changed rows. If LanceDB delete/upsert fails, the SQLite write is preserved and vector state becomes `needs_repair` instead of surfacing the truth-row write as failed.

`scope_recall_stats` reports:

- `vector.row_count` — physical LanceDB row count
- `vector.unique_id_count` — distinct vector ids
- `vector.duplicate_row_count` — extra physical rows beyond one row per id
- `vector.status` — `ready`, `degraded`, `needs_repair`, `disabled`, or `error`

A healthy synced companion should have `total_memories == vector.unique_id_count == vector.row_count` and `vector.duplicate_row_count == 0` for provider-owned rows.

For deeper maintenance:

```bash
python scripts/repair.vector_index.py --hermes-home "$HERMES_HOME" --dry-run
python scripts/repair.vector_index.py --hermes-home "$HERMES_HOME"
```

## Retrieval modes

Configured in `config.json`:

- `lexical`
- `vector`
- `hybrid` *(default)*

Default hybrid weights:

- lexical: `0.45`
- vector: `0.55`

Freshness / recency knobs are also configurable in `config.json`:

- `freshness_hints`
- `freshness_base_weight`
- `freshness_step_weight`
- `freshness_max_weight`

Freshness detection is token-based rather than substring-based, so unrelated words like `know` / `day` / `date` do not accidentally trigger recency bonuses.

Guardrail: if only one side has a score, that side is used directly instead of being unfairly damped by a missing partner score.

## Scope isolation

Scope is built from:

- `platform`
- `agent_workspace`
- `agent_identity`
- `user_id`
- `gateway_session_key` when available
- otherwise `chat_id`
- plus `thread_id` when present

This prevents the same user from leaking memories across different groups, chats, or topics.

## Authority boundary

Hermes built-in curated memory remains authoritative in:

- `$HERMES_HOME/memories/USER.md`
- `$HERMES_HOME/memories/MEMORY.md`

`scope-recall` reads those files live during recall. It does **not** mirror built-in `memory` tool writes into SQLite, which avoids stale duplicates after replace/remove operations. The `on_memory_write` hook is intentionally retained as an observational no-op so Hermes may notify the provider without changing storage ownership.

## Provider tools

Primary-agent only:

- `scope_recall_store`
- `scope_recall_search`
- `scope_recall_forget`
- `scope_recall_update`
- `scope_recall_dedupe`
- `scope_recall_merge`
- `scope_recall_export`
- `scope_recall_govern`
- `scope_recall_repair`
- `scope_recall_stats`

Backward-compatible aliases are still accepted internally for old `lancepro_*` tool names during transition.

### Tool quick reference

| Tool | Purpose |
| --- | --- |
| `scope_recall_store` | Store a provider-owned memory row after deterministic governance checks |
| `scope_recall_search` | Search scoped memory with lexical/vector/hybrid retrieval |
| `scope_recall_forget` | Delete memories matching a query or explicit id scope |
| `scope_recall_update` | Replace the content/category of an existing memory |
| `scope_recall_dedupe` | Inspect or collapse exact duplicate rows |
| `scope_recall_merge` | Merge multiple memories into a target row |
| `scope_recall_export` | Export SQLite truth rows as JSON or JSONL |
| `scope_recall_govern` | Review tier distribution and decay/archive candidates |
| `scope_recall_repair` | Repair/rebuild the LanceDB companion from SQLite truth |
| `scope_recall_stats` | Inspect storage, retrieval, scope, and vector health |

## Write-time governance

Provider-owned captures now apply a deterministic first line of governance before SQLite writes:

- exact normalized-content dedupe within `(scope_id, target)`
- conservative semantic near-duplicate merge for `user`, `ops`, and `project` memories
- conflict preservation when a near-duplicate contains negation / supersession language
- rules-based smart extraction from user turns into preference / ops / project fact candidates
- metadata classification for category, tier, confidence, sensitivity, and expiry review
- noisy maintenance/system prompt filtering
- trivial reply filtering
- obvious secret-bearing text filtering
- overlong prompt-block filtering through `capture_hard_max_chars`
- governance review through `scope_recall_govern`, including core/working/archive tier counts and decay candidates

This is a local deterministic governance layer, not a remote LLM extraction pipeline. It intentionally stays conservative so SQLite remains auditable truth and conflicting memories are preserved rather than silently overwritten.

## Embedders

Currently implemented:

- `local-hash` — offline hashed fallback embedder
- `local-debug` — tiny deterministic test embedder
- `openai-compatible` — configured default path for Gemini/OpenAI-compatible embedding APIs
- `openai` — direct OpenAI embedding endpoint support
- `sentence-transformers` — local embedding model path for SentenceTransformers / Hugging Face checkpoints

Provider aliases `local-model`, `local-embedding`, and `huggingface` also resolve to the `sentence-transformers` backend.

This means `scope-recall` already supports both:

- hosted API embeddings (for example Gemini/OpenAI-compatible or direct OpenAI)
- local embedding models loaded in-process through `sentence-transformers`

## Migration behavior

On first boot, if `$HERMES_HOME/lancepro/` exists and `$HERMES_HOME/scope-recall/` does not yet contain the new DB/config, the provider:

- copies the legacy SQLite database into the new location
- copies `config.json` forward
- records migration info in `scope_recall_stats`

OpenClaw `memory-lancedb-pro` history is handled separately as an explicit import problem, not automatic compatibility. See:

- `docs/migration.md`
- `docs/differences-from-memory-lancedb-pro.md`
- `scripts/import.openclaw.memory_lancedb_pro.py`

## Troubleshooting

### Recall returns stale or irrelevant context

Check that the running provider is `scope-recall`, not the deprecated `lancepro` name, and remember that live Hermes runtime freshness requires a process restart/reload after code changes.

```bash
hermes memory status
```

### Vector stats show duplicate rows

Run the repair script. SQLite remains truth; the vector layer is rebuildable companion state.

```bash
python scripts/repair.vector_index.py --hermes-home "$HERMES_HOME" --dry-run
python scripts/repair.vector_index.py --hermes-home "$HERMES_HOME"
```

### Hosted embeddings are unavailable

The provider should degrade to `local-hash`. That keeps the system usable but lowers semantic quality. Set `GOOGLE_API_KEY` or `OPENAI_API_KEY` in your private environment to use the configured hosted path.

### OpenClaw `.lance` data does not appear automatically

That is expected. OpenClaw history must be explicitly imported into SQLite truth rows before the companion vector index is rebuilt.

## Current V1 limitations

- vector sync is incremental by stable row id / `updated_at`, with duplicate-id/stale-row repair during normal sync; `scripts/repair.vector_index.py` can rebuild the LanceDB companion from SQLite truth when deeper storage hygiene is needed
- semantic merge is intentionally conservative and rules/scoring-based; it is not a general-purpose contradiction resolver or LLM reasoning layer
- smart extraction is rules-based for common preference / ops / project-fact sentences; it is not full OpenClaw-style LLM created/merged/skipped extraction parity
- fallback `local-hash` is only a degraded offline path, not a true semantic model
- old `lancepro` directory still exists as a compatibility shim until final cleanup is approved
- the supported Hermes install shape is still an unpacked plugin directory; the wheel is verified as a package artifact, not as a Hermes discovery mechanism

See `docs/stability.md` for the exact V1 compatibility and non-goal boundaries.

## Packaging and release bootstrap

This directory now includes:

- `pyproject.toml`
- `.gitignore`
- `CONTRIBUTING.md`
- `.github/workflows/ci.yml`
- `scripts/check.release.py`
- `docs/stability.md`
- `.env.example`
- `scripts/repair.vector_index.py`

Basic packaging verification target:

```bash
python3 -m pip wheel . --no-deps -w /tmp/scope-recall-dist
```

Important boundary:

- Hermes runtime discovery for this plugin still expects an unpacked plugin directory under `$HERMES_HOME/plugins/scope-recall/`
- a successful wheel build is a packaging sanity check for the Python module, not proof that Hermes can discover or install the plugin directly from that wheel
- do not treat wheel success alone as live-plugin installation verification unless Hermes later gains an explicit wheel/entry-point install path for this plugin shape

## Test status

Current focused regression coverage includes:

- plugin loading from `$HERMES_HOME/plugins`
- hybrid recall returning semantically matched content
- built-in curated memory reflection
- vector state visible in stats
- runtime fallback from unavailable API embeddings to `local-hash`
- vector table rebuild when embedder dimensions change
- vector duplicate physical rows are repaired back to one row per id
- vector delete/upsert failure preserves SQLite truth and marks vector status `needs_repair`
- vector search failure degrades to lexical recall and marks vector status `needs_repair`
- write-time exact dedupe prevents repeat SQLite rows for the same normalized content in the same scope/target
- capture filtering blocks known maintenance prompts, trivial replies, obvious secret-bearing text, and overlong prompt blocks
- semantic near-duplicate merge and conflict preservation
- rules-based smart extraction from user turns into preference / ops / project fact memories
- merge / export / govern provider tools
- governance metadata classification and decay review candidates
- provider tools cover store/search/forget/update/dedupe/merge/export/govern/repair/stats
- explicit vector companion rebuild from SQLite truth via `scripts/repair.vector_index.py`
- release gate automation via `scripts/check.release.py`
- `scope_recall_stats` exposes physical rows, unique ids, and duplicate-row count
- top-level `import scope_recall` stays light without Hermes runtime modules
- `on_memory_write` remains an intentional observational no-op

The repository is structured for GitHub publication as a stable V1 Hermes memory provider. Legacy `lancepro` compatibility remains intentionally covered by focused migration and alias tests during the deprecation window.
