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

