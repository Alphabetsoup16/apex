from __future__ import annotations


def extract_first_json_object(text: str) -> str:
    """
    Extract the first top-level JSON object from a string.

    This avoids brittle regexes and keeps the orchestrator resilient to small
    wrapper text like "Here is the JSON:".
    """

    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object start ('{') found")

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    raise ValueError("JSON object not closed")
