from apex.models import CodeFile, CodeSolution, TextCompletion
from apex.scoring import DecisionSignals, code_signature, decide_verdict, text_convergence


def test_text_convergence_identical_answers_and_claims():
    v1 = TextCompletion(answer="hello world", key_claims=["x"])
    v2 = TextCompletion(answer="hello world", key_claims=["x"])
    assert text_convergence([v1, v2]) == 1.0


def test_text_convergence_penalizes_claim_mismatch():
    v1 = TextCompletion(answer="hello world", key_claims=["x"])
    v2 = TextCompletion(answer="hello world", key_claims=["different"])
    assert text_convergence([v1, v2]) < 1.0


def test_code_signature_syntax_error():
    sol = CodeSolution(files=[CodeFile(path="solution.py", content="def bad(:")])
    assert code_signature(sol) == tuple()


def test_decide_verdict_text_high_verified():
    signals = DecisionSignals(
        convergence=0.99,
        adversarial_high=False,
        adversarial_medium=False,
        execution_pass=None,
        execution_required=False,
        extraction_ok=True,
    )
    assert decide_verdict(signals) == "high_verified"


def test_decide_verdict_code_no_execution_downgrades():
    signals = DecisionSignals(
        convergence=0.99,
        adversarial_high=False,
        adversarial_medium=False,
        execution_pass=None,
        execution_required=True,
        extraction_ok=True,
    )
    assert decide_verdict(signals) == "needs_review"
