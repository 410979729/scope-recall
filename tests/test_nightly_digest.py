from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scope_recall.nightly_digest import DigestOptions, load_session_bundles, redact_sensitive, run_digest
from scope_recall.sql_store import delete_rows


def _ts(day: date, hour: int = 12) -> float:
    return datetime(day.year, day.month, day.day, hour, 0, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()


def _write_config(hermes_home: Path) -> None:
    storage_dir = hermes_home / "scope-recall"
    storage_dir.mkdir(parents=True, exist_ok=True)
    (storage_dir / "config.json").write_text(json.dumps({"vector": {"enabled": False}}), encoding="utf-8")


def _create_state_db(path: Path, day: date, *, content_suffix: str = "") -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                user_id TEXT,
                model TEXT,
                title TEXT,
                started_at REAL NOT NULL
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                tool_calls TEXT,
                tool_name TEXT,
                timestamp REAL NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO sessions(id, source, user_id, model, title, started_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("session-task", "telegram", "8176453077", "deepseek-v4-pro", "scope-recall live validation", _ts(day, 9)),
        )
        tool_calls = [
            {
                "type": "function",
                "function": {
                    "name": "terminal",
                    "arguments": json.dumps({"command": "python -m pytest -q && python scripts/check.release.py"}),
                },
            },
            {"type": "function", "function": {"name": "read_file", "arguments": "{}"}},
        ]
        messages = [
            ("user", f"帮我验证 scope-recall 插件并修复记忆能力。API_KEY=secret1234567890 {content_suffix}", "", ""),
            ("assistant", "我会先读代码，再跑测试，最后做玉衡实机 smoke。", json.dumps(tool_calls), ""),
            ("tool", "{\"output\":\"117 passed, release gate ok, token=abcdef1234567890\"}", "", "terminal"),
            ("assistant", "完成：pytest 117 passed，release gate ok，玉衡 live smoke 验证通过。", "", ""),
        ]
        for role, content, calls, tool_name in messages:
            conn.execute(
                "INSERT INTO messages(session_id, role, content, tool_calls, tool_name, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                ("session-task", role, content, calls, tool_name, _ts(day, 10)),
            )
        conn.commit()
    finally:
        conn.close()


def test_redact_sensitive_handles_assignment_and_bearer_without_leaking_secret():
    fake_bearer = "abcd" + "efgh" + "ijkl" + "mnopqrstuvwxyz"
    text = redact_sensitive("api_key=sk-secretsecretsecret bearer " + fake_bearer)
    assert "sk-secret" not in text
    assert fake_bearer not in text
    assert "[REDACTED]" in text


def test_load_session_bundles_keeps_tool_summary_but_not_raw_tool_content(tmp_path):
    day = date(2026, 6, 1)
    db_path = tmp_path / "state.db"
    _create_state_db(db_path, day)

    bundles = load_session_bundles(db_path, digest_date=day, timezone_name="Asia/Shanghai")

    assert len(bundles) == 1
    bundle = bundles[0]
    assert bundle.is_task is True
    assert "terminal" in bundle.tool_names
    assert "read_file" in bundle.tool_names
    assert any("pytest" in command for command in bundle.command_hints)
    assert not any(message.role == "tool" and "secret1234567890" in message.content for message in bundle.messages)


def test_heuristic_digest_writes_workflow_memory_and_ledger_then_skips_duplicate(tmp_path):
    day = date(2026, 6, 1)
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    _write_config(hermes_home)
    _create_state_db(hermes_home / "state.db", day)

    options = DigestOptions(hermes_home=hermes_home, digest_date=day, extractor="heuristic")
    first = run_digest(options)

    assert first["ok"] is True
    assert first["inserted"] == 1
    conn = sqlite3.connect(hermes_home / "scope-recall" / "memory.sqlite3")
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT id, target, content, metadata FROM memories").fetchall()
        assert len(rows) == 1
        assert rows[0]["target"] == "ops"
        assert "工具链" in rows[0]["content"]
        assert "secret1234567890" not in rows[0]["content"]
        metadata = json.loads(rows[0]["metadata"])
        assert metadata["memory_type"] == "workflow"
        assert "terminal" in metadata["tools_used"]
        assert conn.execute("SELECT COUNT(*) FROM nightly_digest_runs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM memory_digest_sources").fetchone()[0] == 1
    finally:
        conn.close()

    second = run_digest(options)
    assert second["inserted"] == 0
    assert second["skipped"] >= 1
    conn = sqlite3.connect(hermes_home / "scope-recall" / "memory.sqlite3")
    conn.row_factory = sqlite3.Row
    try:
        assert conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 1
        memory_id = conn.execute("SELECT id FROM memories").fetchone()[0]
        assert delete_rows(conn, [memory_id]) == 1
        assert conn.execute("SELECT COUNT(*) FROM memory_digest_sources WHERE memory_id = ?", (memory_id,)).fetchone()[0] == 0
    finally:
        conn.close()


def test_dry_run_does_not_write_digest_rows(tmp_path):
    day = date(2026, 6, 1)
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    _write_config(hermes_home)
    _create_state_db(hermes_home / "state.db", day)

    result = run_digest(DigestOptions(hermes_home=hermes_home, digest_date=day, extractor="heuristic", dry_run=True))

    assert result["ok"] is True
    assert result["status"] == "dry_run"
    assert not (hermes_home / "scope-recall" / "memory.sqlite3").exists()
