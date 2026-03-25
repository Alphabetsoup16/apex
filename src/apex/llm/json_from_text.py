from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from apex.safety.validators import extract_first_json_object

_JSON_INVALID_SUFFIX = (
    "\n\nIMPORTANT: Your previous output was not valid JSON. "
    "Output ONLY a single valid JSON object and nothing else."
)


def retry_user_reset_to_base_with_suffix(base_user: str, _current_user: str) -> str:
    """After a failed parse, send one remedial suffix anchored to the original user message."""
    return base_user + _JSON_INVALID_SUFFIX


def retry_user_append_suffix(_base_user: str, current_user: str) -> str:
    """After a failed parse, append the remedial suffix (cumulative; matches Anthropic behavior)."""
    return current_user + _JSON_INVALID_SUFFIX


async def complete_json_object_via_text_attempts(
    *,
    fetch_text: Callable[[int, str], Awaitable[str]],
    initial_user: str,
    max_attempts: int,
    on_parse_failure_advance_user: Callable[[str, str], str],
    failure_label: str,
) -> dict[str, Any]:
    """
    Shared JSON-object extraction: call ``fetch_text(attempt_index, user)``, parse JSON, retry.

    ``on_parse_failure_advance_user(base_user, current_user)`` returns the user string for the
    next attempt (reset vs cumulative strategy is provider-specific).
    """
    parse_err: Exception | None = None
    user_current = initial_user
    base_user = initial_user

    for attempt in range(max_attempts):
        text = await fetch_text(attempt, user_current)
        try:
            return json.loads(extract_first_json_object(text))
        except asyncio.CancelledError:
            raise
        except (json.JSONDecodeError, ValueError, TypeError, KeyError) as e:
            parse_err = e
            user_current = on_parse_failure_advance_user(base_user, user_current)

    raise RuntimeError(
        f"Failed to obtain valid JSON from {failure_label}: {parse_err}"
    ) from parse_err
