from apex.code_ground_truth.executor_client import HttpExecutionBackend


def test_execute_url_headers_default_empty():
    b = HttpExecutionBackend("http://example.com/api")
    assert b._auth_headers == {}


def test_execute_url_appends_execute_when_missing():
    b = HttpExecutionBackend("http://example.com/api")
    assert b._execute_url() == "http://example.com/api/execute"


def test_execute_url_does_not_duplicate_execute_when_present():
    b = HttpExecutionBackend("http://example.com/api/execute")
    assert b._execute_url() == "http://example.com/api/execute"

