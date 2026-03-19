import pytest

from apex.models import CodeFile, CodeSolution, CodeTests
from apex.orchestrator import validate_code_bundles


def test_validate_code_bundles_missing_solution_py():
    sol = CodeSolution(files=[CodeFile(path="other.py", content="x=1")])
    tests = CodeTests(files=[CodeFile(path="test_solution.py", content="assert True")])
    with pytest.raises(ValueError) as e:
        validate_code_bundles(sol, tests)
    assert str(e.value) == "missing_solution_py"


def test_validate_code_bundles_missing_test_solution_py():
    sol = CodeSolution(files=[CodeFile(path="solution.py", content="def f():\n    return 1")])
    tests = CodeTests(files=[CodeFile(path="other_test.py", content="assert True")])
    with pytest.raises(ValueError) as e:
        validate_code_bundles(sol, tests)
    assert str(e.value) == "missing_test_solution_py"


def test_validate_code_bundles_ok():
    sol = CodeSolution(files=[CodeFile(path="solution.py", content="def f():\n    return 1")])
    tests = CodeTests(
        files=[CodeFile(path="test_solution.py", content="def test_f():\n    assert True")]
    )
    validate_code_bundles(sol, tests)
