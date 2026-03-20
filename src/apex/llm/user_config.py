from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

CONFIG_VERSION = 1
# Default for `apex init`: fast/cheap tier fits APEX's many LLM calls per run.
DEFAULT_ANTHROPIC_MODEL = "claude-3-5-haiku-latest"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"


def user_config_path() -> Path:
    """
    User LLM config file location.

    Override with ``APEX_USER_CONFIG_PATH`` (absolute or ``~``-expanded path) for tests
    or custom layouts.
    """
    override = os.environ.get("APEX_USER_CONFIG_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".apex" / "config.json"


def load_user_llm_config() -> dict[str, Any]:
    """Return parsed JSON object from the user config file, or {} if missing/invalid."""
    path = user_config_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_user_llm_config(data: dict[str, Any]) -> Path:
    """
    Write config atomically and restrict permissions on POSIX (owner read/write only).
    """
    path = user_config_path()
    parent = path.parent
    parent_existed = parent.exists()
    parent.mkdir(parents=True, exist_ok=True)
    if not parent_existed and os.name == "posix":
        try:
            parent.chmod(0o700)
        except OSError:
            pass

    payload = {"version": CONFIG_VERSION, **data}
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        if os.name == "posix":
            try:
                tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
        tmp.replace(path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    if os.name == "posix":
        try:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    return path


def clear_user_llm_config() -> bool:
    """Remove the config file if it exists. Returns True if a file was removed."""
    path = user_config_path()
    try:
        path.unlink()
        return True
    except OSError:
        return False
