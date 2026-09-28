from app.security import hash_password, hash_token, new_token, verify_password


def test_password_hash_roundtrip():
    stored = hash_password("s3cret!")
    assert stored.startswith("scrypt$")
    assert "s3cret!" not in stored
    assert verify_password("s3cret!", stored)
    assert not verify_password("wrong", stored)


def test_password_hashes_are_salted():
    assert hash_password("same") != hash_password("same")


def test_malformed_hash_does_not_verify():
    assert not verify_password("x", "not-a-hash")
    assert not verify_password("x", "bcrypt$1$2$3$abc$def")


def test_tokens_are_long_random_and_hashed():
    a, b = new_token(), new_token()
    assert a != b
    assert len(a) >= 43  # 32 random bytes, base64url
    assert hash_token(a) == hash_token(a)
    assert hash_token(a) != a and len(hash_token(a)) == 64
