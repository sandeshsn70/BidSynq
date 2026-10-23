import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app import ratelimit
from app.config import settings
from app.security import ALGORITHM, create_access_token, hash_password, verify_password
from tests.conftest import PASSWORD

REGISTER = {"name": "Asha Rao", "email": "Asha@Example.com", "password": PASSWORD, "role": "buyer", "company_name": "Rao Ltd"}


def test_register_login_me_roundtrip(client):
    r = client.post("/auth/register", json=REGISTER)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == "asha@example.com" and body["role"] == "buyer"
    assert "password" not in body and "password_hash" not in body

    r = client.post("/auth/login", json={"email": "ASHA@example.com", "password": PASSWORD})
    assert r.status_code == 200
    token = r.json()["access_token"]
    assert r.json()["token_type"] == "bearer"

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == "asha@example.com"
    assert "password_hash" not in me.json()


def test_duplicate_email_rejected_case_insensitively(client):
    assert client.post("/auth/register", json=REGISTER).status_code == 201
    again = client.post("/auth/register", json={**REGISTER, "email": "asha@EXAMPLE.com"})
    assert again.status_code == 409


@pytest.mark.parametrize("patch", [
    {"password": "short"}, {"email": "not-an-email"}, {"name": " "}, {"role": "superuser"},
])
def test_registration_validation(client, patch):
    assert client.post("/auth/register", json={**REGISTER, **patch}).status_code == 422


def test_admin_registration_blocked_by_default(client):
    r = client.post("/auth/register", json={**REGISTER, "role": "admin"})
    assert r.status_code == 400


def test_admin_registration_only_when_explicitly_enabled(client, monkeypatch):
    monkeypatch.setattr(settings, "bidsynq_allow_admin_registration", True)
    r = client.post("/auth/register", json={**REGISTER, "role": "admin"})
    assert r.status_code == 201 and r.json()["role"] == "admin"


def test_wrong_password_and_unknown_user_share_one_message(client):
    client.post("/auth/register", json=REGISTER)
    bad_pw = client.post("/auth/login", json={"email": REGISTER["email"], "password": "WrongPassword1"})
    unknown = client.post("/auth/login", json={"email": "nobody@example.com", "password": "WrongPassword1"})
    assert bad_pw.status_code == unknown.status_code == 401
    assert bad_pw.json() == unknown.json()


def test_login_is_rate_limited_per_account(client):
    client.post("/auth/register", json=REGISTER)
    for _ in range(ratelimit.MAX_FAILURES):
        assert client.post("/auth/login", json={"email": REGISTER["email"], "password": "nope-nope"}).status_code == 401
    blocked = client.post("/auth/login", json={"email": REGISTER["email"], "password": PASSWORD})
    assert blocked.status_code == 429


def test_password_hashing_and_verification():
    hashed = hash_password("S3cret-pass")
    assert hashed.startswith("$2b$") and "S3cret" not in hashed
    assert verify_password("S3cret-pass", hashed)
    assert not verify_password("s3cret-pass", hashed)
    assert not verify_password("x", "not-a-hash") and not verify_password("x", "")


def test_legacy_2a_bcrypt_hashes_still_verify():
    # Hashes written by older versions (passlib) may use the $2a$/$2y$ prefixes.
    hashed = hash_password("legacy-pass-1")
    assert verify_password("legacy-pass-1", "$2a$" + hashed[4:])
    assert verify_password("legacy-pass-1", "$2y$" + hashed[4:])


def test_long_passwords_do_not_crash():
    long_password = "p" * 128
    assert verify_password(long_password, hash_password(long_password))


def test_missing_token_is_401(client):
    r = client.get("/auth/me")
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def _token(payload, key=None, alg=ALGORITHM):
    return jwt.encode(payload, key or settings.secret_key, algorithm=alg)


def test_expired_token_rejected(client, buyer):
    expired = _token({"sub": str(buyer.id), "iat": int(time.time()) - 7200, "exp": int(time.time()) - 3600})
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


@pytest.mark.parametrize("make", [
    lambda uid: "garbage.token.value",
    lambda uid: _token({"sub": str(uid), "exp": int(time.time()) + 600}, key="a-different-secret-key-of-32-chars-xx"),
    lambda uid: _token({"sub": str(uid)}),                                      # no exp
    lambda uid: _token({"exp": int(time.time()) + 600}),                        # no sub
    lambda uid: _token({"sub": "abc", "exp": int(time.time()) + 600}),          # non-numeric subject
    lambda uid: _token({"sub": "999999", "exp": int(time.time()) + 600}),       # unknown user
    lambda uid: jwt.encode({"sub": str(uid), "exp": int(time.time()) + 600}, None, algorithm="none"),  # alg=none
])
def test_invalid_tokens_rejected(client, buyer, make):
    token = make(buyer.id)
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_token_has_expiry_and_subject(buyer):
    claims = jwt.decode(create_access_token(buyer.id), settings.secret_key, algorithms=[ALGORITHM])
    assert claims["sub"] == str(buyer.id)
    assert 0 < claims["exp"] - claims["iat"] <= settings.access_token_minutes * 60 + 5


def test_role_is_read_from_database_not_token(client, buyer, Session):
    from app.models import User
    headers = buyer.headers
    assert client.get("/dashboard/summary", headers=headers).json()["role"] == "buyer"
    with Session() as s:
        s.get(User, buyer.id).role = "supplier"
        s.commit()
    assert client.get("/dashboard/summary", headers=headers).json()["role"] == "supplier"


def test_role_guard_on_protected_routes(client, supplier, buyer, admin):
    t = {"title": "Something valid", "deadline": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}
    assert client.post("/tenders", json=t, headers=supplier.headers).status_code == 403
    assert client.get("/audit/verify", headers=buyer.headers).status_code == 403
    assert client.get("/audit/verify", headers=supplier.headers).status_code == 403
    assert client.get("/audit/verify", headers=admin.headers).status_code == 200
    assert client.get("/tenders").status_code == 401
