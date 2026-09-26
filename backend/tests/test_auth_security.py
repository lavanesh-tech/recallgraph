import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from recallgraph.auth.passwords import hash_password, needs_rehash, verify_password
from recallgraph.auth.tokens import (
    ALGORITHM,
    TokenError,
    create_access_token,
    decode_access_token,
    hash_refresh_token,
    new_refresh_token,
)
from recallgraph.core.config import Settings

SETTINGS = Settings(environment="test")


def test_argon2id_hash_verifies_and_rejects() -> None:
    digest = hash_password("correct horse battery staple")

    assert digest.startswith("$argon2id$")
    assert verify_password(digest, "correct horse battery staple")
    assert not verify_password(digest, "wrong password entirely")
    assert not verify_password("not-a-hash", "anything")
    assert not needs_rehash(digest)


def test_access_token_round_trip() -> None:
    user_id = uuid.uuid4()
    token, ttl = create_access_token(user_id, SETTINGS)

    assert ttl == SETTINGS.access_token_ttl_s
    assert decode_access_token(token, SETTINGS) == user_id


def test_expired_token_is_rejected() -> None:
    token, _ = create_access_token(uuid.uuid4(), SETTINGS, ttl_s=-5)

    with pytest.raises(TokenError, match="ExpiredSignature"):
        decode_access_token(token, SETTINGS)


def test_tampered_token_is_rejected() -> None:
    token, _ = create_access_token(uuid.uuid4(), SETTINGS)
    header, payload, signature = token.split(".")
    mid = len(signature) // 2
    flipped = "B" if signature[mid] == "A" else "A"
    tampered = f"{header}.{payload}.{signature[:mid]}{flipped}{signature[mid + 1 :]}"

    with pytest.raises(TokenError):
        decode_access_token(tampered, SETTINGS)


def test_token_signed_with_another_key_is_rejected() -> None:
    other = Settings(environment="test", jwt_secret="x" * 40)
    token, _ = create_access_token(uuid.uuid4(), other)

    with pytest.raises(TokenError, match="InvalidSignature"):
        decode_access_token(token, SETTINGS)


def test_wrong_audience_and_unsigned_tokens_are_rejected() -> None:
    now = datetime.now(UTC)
    claims = {
        "sub": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "jti": "x",
        "typ": "access",
        "iss": SETTINGS.jwt_issuer,
    }
    key = SETTINGS.jwt_secret.get_secret_value()
    wrong_aud = jwt.encode({**claims, "aud": "someone-else"}, key, algorithm=ALGORITHM)
    unsigned = jwt.encode({**claims, "aud": SETTINGS.jwt_audience}, "", algorithm="none")

    for token in (wrong_aud, unsigned):
        with pytest.raises(TokenError):
            decode_access_token(token, SETTINGS)


def test_non_access_token_type_is_rejected() -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "jti": "x",
            "typ": "refresh",
            "iss": SETTINGS.jwt_issuer,
            "aud": SETTINGS.jwt_audience,
        },
        SETTINGS.jwt_secret.get_secret_value(),
        algorithm=ALGORITHM,
    )

    with pytest.raises(TokenError, match="wrong token type"):
        decode_access_token(token, SETTINGS)


def test_refresh_tokens_are_random_and_stored_hashed() -> None:
    raw_a, hash_a = new_refresh_token()
    raw_b, _ = new_refresh_token()

    assert raw_a != raw_b
    assert hash_a == hash_refresh_token(raw_a)
    assert raw_a not in hash_a and len(hash_a) == 64
