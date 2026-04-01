from __future__ import annotations

import pytest

from app.cli import commands


def test_require_current_schema_passes_when_database_is_current(monkeypatch):
    monkeypatch.setattr(commands, "_get_schema_revisions", lambda: ("003_add_latest_positions", "003_add_latest_positions"))

    commands._require_current_schema()


def test_require_current_schema_exits_with_actionable_message_when_database_is_behind(monkeypatch):
    monkeypatch.setattr(commands, "_get_schema_revisions", lambda: ("002_add_raw_payload_text", "003_add_latest_positions"))

    with pytest.raises(SystemExit) as exc_info:
        commands._require_current_schema()

    assert (
        str(exc_info.value)
        == "Database schema is out of date (current: 002_add_raw_payload_text, expected: 003_add_latest_positions). Run `alembic upgrade head` and retry."
    )


def test_import_live_carriers_command_is_registered():
    assert "import_live_carriers" in commands.COMMANDS
