from app.core.security import create_access_token, decode_access_token


def test_access_tokens_issued_in_the_same_instant_are_still_unique() -> None:
    """Regression test: before the `jti` claim was added, two tokens for the
    same subject issued within the same second were byte-for-byte identical,
    since iat/exp only carry second resolution and nothing else varied.
    """
    # A properly-length secret (32+ bytes), not a short placeholder — PyJWT
    # now warns (InsecureKeyLengthWarning) on short HMAC keys per RFC 7518
    # §3.2, a real signal worth respecting even in a test that isn't
    # actually testing key-length handling itself.
    kwargs = {
        "subject": "user-123",
        "secret": "test-secret-with-plenty-of-entropy-for-hs256-abcdef123456",
        "algorithm": "HS256",
        "expires_minutes": 30,
    }

    token_a = create_access_token(**kwargs)
    token_b = create_access_token(**kwargs)

    assert token_a != token_b

    claims_a = decode_access_token(token_a, secret=kwargs["secret"], algorithm="HS256")
    claims_b = decode_access_token(token_b, secret=kwargs["secret"], algorithm="HS256")
    assert claims_a["jti"] != claims_b["jti"]
    assert claims_a["sub"] == claims_b["sub"] == "user-123"
