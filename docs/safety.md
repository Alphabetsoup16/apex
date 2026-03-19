# Safety & Auditing

APEX contains lightweight safety checks designed to reduce common failure modes.

## Secret redaction

Before sending prompts to the LLM, APEX applies heuristic redaction to remove common secret patterns.

## Chain-of-thought auditing (CoT)

APEX runs a deterministic, conservative auditor that blocks when it detects common chain-of-thought leakage markers:

- Text mode: it inspects `answer` and `key_claims`
- Code mode: it inspects the generated solution code content

When leakage is detected:

- the run is `blocked`
- `metadata.cot_audit` is included

Note: CoT auditing is heuristic and intentionally errs on the side of blocking.

## Doc-only inspection (code mode)

In `mode=code`, APEX also runs an additional “inspection” pass that relies on LLM knowledge (no external doc retrieval yet).

Policy:
- Findings with `severity="high"` can affect the verdict (may block or downgrade outcomes)
- Findings with `severity="medium"` or `severity="low"` are included for reporting, but do not affect the verdict yet

This stage is designed to be extensible later (e.g., swap in doc retrieval via Context7 or static analyzers per language).

