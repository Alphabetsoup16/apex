from __future__ import annotations

import ast
import difflib
from dataclasses import dataclass

from apex.models import CodeSolution, TextCompletion


def _normalize_ws(s: str) -> str:
    return " ".join(s.split())


def _normalize_claim(s: str) -> str:
    # Lowercase + remove non-alphanumerics; keep it simple and deterministic.
    s = s.strip().lower()
    s = "".join(ch for ch in s if ch.isalnum() or ch.isspace())
    return " ".join(s.split())


def _pairwise_average_similarity(a: list[str], b: list[str]) -> float:
    """
    Average best-match similarity between two claim sets.
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0

    a_norm = [_normalize_claim(x) for x in a if x.strip()]
    b_norm = [_normalize_claim(x) for x in b if x.strip()]
    if not a_norm and not b_norm:
        return 1.0
    if not a_norm or not b_norm:
        return 0.0

    # Best-match from A to B.
    scores_a_to_b: list[float] = []
    for ca in a_norm:
        best = 0.0
        for cb in b_norm:
            best = max(best, difflib.SequenceMatcher(a=ca, b=cb).ratio())
        scores_a_to_b.append(best)

    # Symmetrize by best-match from B to A.
    scores_b_to_a: list[float] = []
    for cb in b_norm:
        best = 0.0
        for ca in a_norm:
            best = max(best, difflib.SequenceMatcher(a=ca, b=cb).ratio())
        scores_b_to_a.append(best)

    a_to_b = sum(scores_a_to_b) / max(1, len(scores_a_to_b))
    b_to_a = sum(scores_b_to_a) / max(1, len(scores_b_to_a))
    return (a_to_b + b_to_a) / 2.0


def text_convergence(variants: list[TextCompletion]) -> float:
    if len(variants) <= 1:
        return 1.0

    answers = [_normalize_ws(v.answer) for v in variants]
    key_claims = [v.key_claims for v in variants]

    # Average pairwise similarity: combine answer wording + claim-set agreement.
    pairs: list[float] = []
    for i in range(len(answers)):
        for j in range(i + 1, len(answers)):
            answer_sim = difflib.SequenceMatcher(a=answers[i], b=answers[j]).ratio()
            claims_sim = _pairwise_average_similarity(key_claims[i], key_claims[j])
            pairs.append(0.7 * answer_sim + 0.3 * claims_sim)
    return sum(pairs) / max(1, len(pairs))


def code_signature(solution: CodeSolution) -> tuple[str, ...]:
    """
    Very lightweight, deterministic signature for “is this the same solution shape”.
    We avoid deep semantic equivalence (hard) and focus on stable structural features.
    """

    content_by_path = {f.path: f.content for f in solution.files}
    main = content_by_path.get("solution.py")
    if not main:
        # Fall back to first file.
        main = next(iter(content_by_path.values()), "")
    try:
        tree = ast.parse(main)
    except SyntaxError:
        return tuple()

    sig: list[str] = []

    imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    if imports:
        sig.append("imports:" + ",".join(sorted(set(imports))))

    def fn_sig(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        args = fn.args
        arg_counts = (
            len(args.posonlyargs),
            len(args.args),
            len(args.kwonlyargs),
            args.vararg is not None,
            args.kwarg is not None,
        )
        return f"{fn.name}:{arg_counts}"

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sig.append("fn:" + fn_sig(node))
        elif isinstance(node, ast.ClassDef):
            methods: list[str] = []
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(fn_sig(sub))
            sig.append(f"class:{node.name}:methods:{len(methods)}:" + ",".join(sorted(set(methods))))

    return tuple(sorted(sig))


def code_convergence(variants: list[CodeSolution]) -> float:
    if len(variants) <= 1:
        return 1.0
    sigs = [code_signature(v) for v in variants]
    if len(set(sigs)) == 1:
        return 1.0

    pairs: list[float] = []
    for i in range(len(sigs)):
        for j in range(i + 1, len(sigs)):
            a = " ".join(sigs[i])
            b = " ".join(sigs[j])
            sim = difflib.SequenceMatcher(a=a, b=b).ratio()
            pairs.append(sim)
    return sum(pairs) / max(1, len(pairs))


def select_best_text(variants: list[TextCompletion]) -> int:
    """
    Choose the answer that is most similar to the others.
    """

    answers = [_normalize_ws(v.answer) for v in variants]
    claims = [v.key_claims for v in variants]
    best_i = 0
    best_score = -1.0
    for i in range(len(answers)):
        scores: list[float] = []
        for j in range(len(answers)):
            if i == j:
                continue
            answer_sim = difflib.SequenceMatcher(a=answers[i], b=answers[j]).ratio()
            claims_sim = _pairwise_average_similarity(claims[i], claims[j])
            scores.append(0.7 * answer_sim + 0.3 * claims_sim)
        avg = sum(scores) / max(1, len(scores))
        if avg > best_score:
            best_score = avg
            best_i = i
    return best_i


def select_best_code(variants: list[CodeSolution]) -> int:
    sigs = [code_signature(v) for v in variants]
    best_i = 0
    best_score = -1.0
    for i in range(len(sigs)):
        scores: list[float] = []
        for j in range(len(sigs)):
            if i == j:
                continue
            a = " ".join(sigs[i])
            b = " ".join(sigs[j])
            scores.append(difflib.SequenceMatcher(a=a, b=b).ratio())
        avg = sum(scores) / max(1, len(scores))
        if avg > best_score:
            best_score = avg
            best_i = i
    return best_i


@dataclass(frozen=True)
class DecisionSignals:
    convergence: float
    adversarial_high: bool
    adversarial_medium: bool
    execution_pass: bool | None
    execution_required: bool
    extraction_ok: bool


def decide_verdict(signals: DecisionSignals) -> str:
    if not signals.extraction_ok:
        return "blocked"
    if signals.adversarial_high:
        return "blocked"
    if signals.execution_required and signals.execution_pass is False:
        return "blocked"

    # high_verified requires both strong convergence and no high severity.
    if signals.execution_required:
        if (
            signals.execution_pass is True
            and signals.convergence >= 0.98
            and not signals.adversarial_medium
        ):
            return "high_verified"
    else:
        if signals.convergence >= 0.98 and not signals.adversarial_medium:
            return "high_verified"

    return "needs_review"

