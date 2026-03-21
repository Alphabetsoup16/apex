from __future__ import annotations

import sys
import textwrap
from getpass import getpass

from apex.config.env import env_str
from apex.llm.user_config import (
    DEFAULT_ANTHROPIC_BASE_URL,
    DEFAULT_ANTHROPIC_MODEL,
    clear_user_llm_config,
    load_user_llm_config,
    save_user_llm_config,
    user_config_path,
)


def _out(msg: str = "", *, file=sys.stdout) -> None:
    """CLI output (multiline-safe: embed ``\\n`` in ``msg`` or pass triple-quoted strings)."""
    print(msg, file=file)


def cmd_setup() -> None:
    path = user_config_path()
    intro = textwrap.dedent(
        f"""\
        APEX local setup (LLM)
        Config file: {path}

        Choose provider:
          1) Anthropic - API key + model (recommended for local MCP)
          2) GitHub Copilot - not supported as a direct provider.
             Copilot is bound to your editor session; APEX runs as a separate process
             and needs a normal API (Anthropic, or your own OpenAI-compatible proxy).
        """
    ).strip()
    _out(intro)
    _out()

    choice = input("Enter 1 to configure Anthropic, or q to quit [1/q]: ").strip().lower()
    if choice in ("q", "quit"):
        _out("Aborted.")
        return
    if choice and choice != "1":
        _out("Only option 1 is configurable from this wizard right now.", file=sys.stderr)
        raise SystemExit(1)

    _out()
    tip = textwrap.dedent(
        """\
        Model tip: APEX runs many LLM calls (ensemble, reviews, tests).
        Haiku (default below) is fastest/cheapest; try Sonnet if output quality is weak;
        Opus is usually overkill here.
        """
    ).strip()
    _out(tip)
    _out()

    key = getpass("Anthropic API key (input hidden): ").strip()
    if not key:
        _out("No API key entered.", file=sys.stderr)
        raise SystemExit(1)

    model = input(f"Model [{DEFAULT_ANTHROPIC_MODEL}]: ").strip() or DEFAULT_ANTHROPIC_MODEL
    base_default = DEFAULT_ANTHROPIC_BASE_URL
    base_in = input(f"Base URL [{base_default}]: ").strip() or base_default

    save_user_llm_config(
        {
            "provider": "anthropic",
            "anthropic_api_key": key,
            "anthropic_model": model,
            "anthropic_base_url": base_in,
        }
    )
    _out()
    _out(f"Wrote {path}")
    _out("Tip: environment variables still override this file (see docs/configuration.md).")
    _out("Same wizard: `apex setup` (alias of `apex init`).")


def cmd_show() -> None:
    path = user_config_path()
    fc = load_user_llm_config()
    lines = [
        f"Config file: {path}",
        f"  exists: {path.is_file()}",
    ]
    if fc:
        prov = fc.get("provider", "?")
        lines.append(f"  provider (file): {prov}")
        if prov == "anthropic":
            lines.append(f"  model (file): {fc.get('anthropic_model', '') or '(empty)'}")
            lines.append(f"  base_url (file): {fc.get('anthropic_base_url', '') or '(empty)'}")
            key = (fc.get("anthropic_api_key") or "").strip()
            lines.append(
                f"  api_key (file): {'set (' + str(len(key)) + ' chars)' if key else 'empty'}"
            )
    else:
        lines.append("  (no readable file config)")
    lines.append("")
    lines.append("Environment overrides (non-empty values win over file):")
    ak = env_str("ANTHROPIC_API_KEY")
    lines.append(f"  APEX_LLM_PROVIDER={env_str('APEX_LLM_PROVIDER') or '(unset)'}")
    lines.append(f"  ANTHROPIC_API_KEY={'set' if ak else '(unset)'}")
    lines.append(f"  ANTHROPIC_MODEL={env_str('ANTHROPIC_MODEL') or '(unset)'}")
    lines.append(f"  ANTHROPIC_BASE_URL={env_str('ANTHROPIC_BASE_URL') or '(unset)'}")
    _out("\n".join(lines))


def cmd_clear() -> None:
    path = user_config_path()
    if clear_user_llm_config():
        _out(f"Removed {path}")
    else:
        _out(f"No file to remove at {path}")
