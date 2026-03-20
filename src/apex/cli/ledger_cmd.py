from __future__ import annotations

import sqlite3
import sys
import textwrap
from typing import TextIO

from apex.ledger import default_ledger_path, resolve_ledger_db_path


def _out(msg: str = "", *, file: TextIO | None = None) -> None:
    # Resolve stdout at call time so tests (and callers) can monkeypatch ``sys.stdout``.
    print(msg, file=sys.stdout if file is None else file)


def cmd_ledger_summary() -> None:
    """
    Print a short summary of the run ledger (SQLite).
    """
    path = resolve_ledger_db_path()
    if path is None:
        _out(
            textwrap.dedent(
                """\
                Run ledger is disabled (APEX_LEDGER_DISABLED=1).
                Unset APEX_LEDGER_DISABLED to use the default DB at ~/.apex/ledger.sqlite3.
                """
            ).strip(),
            file=sys.stderr,
        )
        raise SystemExit(1)

    if not path.is_file():
        _out(
            textwrap.dedent(
                f"""\
                Ledger database not found yet (no runs recorded):
                  {path}

                Default path: ~/.apex/ledger.sqlite3
                Override: APEX_LEDGER_PATH=/path/to/ledger.sqlite3
                Disable: APEX_LEDGER_DISABLED=1
                """
            ).strip()
        )
        return

    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        total = conn.execute("SELECT COUNT(*) FROM runs;").fetchone()[0]
        by_verdict = conn.execute(
            "SELECT verdict, COUNT(*) AS n FROM runs GROUP BY verdict ORDER BY verdict;"
        ).fetchall()
        bad_trace = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE trace_validation_ok = 0;"
        ).fetchone()[0]
        recent = conn.execute(
            """
            SELECT run_id, created_at, verdict, mode
            FROM runs
            ORDER BY created_at DESC
            LIMIT 8;
            """
        ).fetchall()
    except sqlite3.OperationalError as e:
        _out(f"Could not read ledger (schema missing or corrupt): {e}", file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        conn.close()

    lines = [
        f"Ledger: {path}",
        f"Default (when APEX_LEDGER_PATH unset): {default_ledger_path()}",
        "",
        f"Total runs: {total}",
        "By verdict:",
    ]
    for verdict, n in by_verdict:
        lines.append(f"  {verdict}: {n}")
    lines.append("")
    lines.append(f"Runs with trace_validation_ok=0: {bad_trace}")
    lines.append("")
    lines.append("Recent runs (newest first):")
    if not recent:
        lines.append("  (none)")
    else:
        for run_id, created_at, verdict, mode in recent:
            lines.append(f"  {created_at}  {verdict:14}  mode={mode!s}  {run_id}")
    _out("\n".join(lines))
