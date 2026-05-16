SCOPE_RECALL_STORE_SCHEMA = {
    "name": "scope_recall_store",
    "description": "Store a durable memory in the local Scope Recall provider.",
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Memory text to store."},
            "target": {
                "type": "string",
                "description": "Optional category such as user or memory.",
                "enum": ["user", "memory", "project", "ops", "general"],
            },
        },
        "required": ["content"],
    },
}

SCOPE_RECALL_SEARCH_SCHEMA = {
    "name": "scope_recall_search",
    "description": "Search local Scope Recall memories relevant to a query.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to search for."},
            "limit": {"type": "integer", "description": "Maximum results to return."},
        },
        "required": ["query"],
    },
}

SCOPE_RECALL_FORGET_SCHEMA = {
    "name": "scope_recall_forget",
    "description": "Delete local Scope Recall memories matching a query.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Query used to find memories to delete."},
            "limit": {"type": "integer", "description": "Maximum matching memories to delete."},
        },
        "required": ["query"],
    },
}

SCOPE_RECALL_UPDATE_SCHEMA = {
    "name": "scope_recall_update",
    "description": "Update a local Scope Recall memory by id.",
    "parameters": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "Memory id to update."},
            "content": {"type": "string", "description": "Replacement memory text."},
            "target": {
                "type": "string",
                "description": "Optional replacement category.",
                "enum": ["user", "memory", "project", "ops", "general"],
            },
        },
        "required": ["id", "content"],
    },
}

SCOPE_RECALL_DEDUPE_SCHEMA = {
    "name": "scope_recall_dedupe",
    "description": "Find or collapse exact duplicate Scope Recall memories. Operator-only: requires maintenance_tools_enabled=true.",
    "parameters": {
        "type": "object",
        "properties": {
            "dry_run": {"type": "boolean", "description": "Inspect only; default true."},
            "scope_only": {"type": "boolean", "description": "Restrict dedupe to the current runtime scope."},
        },
    },
}

SCOPE_RECALL_MERGE_SCHEMA = {
    "name": "scope_recall_merge",
    "description": "Merge one or more Scope Recall memories into a target memory.",
    "parameters": {
        "type": "object",
        "properties": {
            "target_id": {"type": "string", "description": "Memory id to keep/update."},
            "source_ids": {"type": "array", "items": {"type": "string"}, "description": "Memory ids to merge then delete."},
            "content": {"type": "string", "description": "Optional explicit merged content."},
            "target": {"type": "string", "enum": ["user", "memory", "project", "ops", "general"]},
        },
        "required": ["target_id"],
    },
}

SCOPE_RECALL_EXPORT_SCHEMA = {
    "name": "scope_recall_export",
    "description": "Export SQLite truth rows as JSON or JSONL. Defaults to the current runtime scope; scope_only=false requires maintenance_tools_enabled=true.",
    "parameters": {
        "type": "object",
        "properties": {
            "format": {"type": "string", "enum": ["jsonl", "json"], "description": "Export format."},
            "scope_only": {"type": "boolean", "description": "Restrict export to current runtime scope; default true."},
        },
    },
}

SCOPE_RECALL_GOVERN_SCHEMA = {
    "name": "scope_recall_govern",
    "description": "Run deterministic memory governance classification and decay review. Operator-only: requires maintenance_tools_enabled=true.",
    "parameters": {
        "type": "object",
        "properties": {
            "dry_run": {"type": "boolean", "description": "Inspect only; default true."},
            "scope_only": {"type": "boolean", "description": "Restrict governance to current runtime scope; default true."},
        },
    },
}

SCOPE_RECALL_REPAIR_SCHEMA = {
    "name": "scope_recall_repair",
    "description": "Repair/rebuild the LanceDB vector companion from SQLite truth. Operator-only: requires maintenance_tools_enabled=true.",
    "parameters": {"type": "object", "properties": {}},
}

SCOPE_RECALL_STATS_SCHEMA = {
    "name": "scope_recall_stats",
    "description": "Show Scope Recall storage, retrieval, and scope statistics.",
    "parameters": {"type": "object", "properties": {}},
}
