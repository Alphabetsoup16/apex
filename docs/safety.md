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

In `mode=code`, APEX runs an **inspection** pass in parallel with adversarial code review (LLM-only today; no external doc retrieval).

**Verdict wiring (today):**

- **Adversarial review:** `high` → can `block`; `medium` → blocks `high_verified` (still `needs_review` if not blocked); `low` → report.
- **Inspection:** only **`high`** is OR’d into the same severity signal as adversarial `high` (so inspection can block). Inspection **`medium` / `low`** do not change `DecisionSignals`; they appear in the inspection payload / review pack only.

Optional **findings policy** may filter **low** findings for display; it **cannot** remove `high` or `medium` (see [configuration.md](configuration.md)).

This stage is designed to be extensible later (e.g., doc retrieval or static analyzers per language).

