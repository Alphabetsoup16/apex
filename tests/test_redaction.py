from apex.safety.redaction import redact_secrets


def test_redact_sk_token():
    text = "here is key sk-abcdefghijklmnopqrstuvwxyz12345 and done"
    out = redact_secrets(text)
    assert "sk-" not in out
    assert "[REDACTED]" in out


def test_redact_password_assignment():
    text = "password='hunter2' and token=abc"
    out = redact_secrets(text)
    assert "hunter2" not in out
    assert "password=" not in out or "[REDACTED]" in out
