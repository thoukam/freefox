from freefox.backends.s3 import _safe_message

def test_secret_redaction():
    text=_safe_message(Exception("Authorization=abc SecretAccessKey=xyz X-Amz-Credential=foo"))
    assert "abc" not in text and "xyz" not in text and "foo" not in text
