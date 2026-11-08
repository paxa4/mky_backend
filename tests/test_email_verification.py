from fastapi.testclient import TestClient

import main
from database import Base, SessionLocal, engine
from email_service import build_verification_link
from models import User


def _client(monkeypatch):
    Base.metadata.create_all(bind=engine)
    sent = []
    monkeypatch.setattr(main, "EMAIL_VERIFICATION_REQUIRED", True)
    monkeypatch.setattr(main, "EMAIL_RESEND_COOLDOWN_SECONDS", 0)
    monkeypatch.setattr(main, "send_verification_email", lambda to, token: sent.append((to, token)))
    return TestClient(main.app), sent


def _cleanup(email):
    db = SessionLocal()
    try:
        db.query(User).filter(User.email == email).delete()
        db.commit()
    finally:
        db.close()


def test_registration_requires_email_confirmation(monkeypatch):
    email = "verify-flow@example.com"
    _cleanup(email)
    client, sent = _client(monkeypatch)

    response = client.post("/auth/register", json={"email": email, "password": "secret123"})
    assert response.status_code == 201
    assert response.json()["email_verified"] is False
    assert len(sent) == 1 and sent[0][0] == email
    token = sent[0][1]
    assert "/verify-email?token=" in build_verification_link(token)

    # до подтверждения войти нельзя
    login = client.post("/auth/login", data={"username": email, "password": "secret123"})
    assert login.status_code == 403

    # повторная отправка письма
    resend = client.post("/auth/resend-verification", json={"email": email})
    assert resend.status_code == 200
    assert len(sent) == 2

    # подтверждение
    verify = client.post("/auth/verify-email", json={"token": token})
    assert verify.status_code == 200

    login = client.post("/auth/login", data={"username": email, "password": "secret123"})
    assert login.status_code == 200
    assert login.json()["user"]["email_verified"] is True

    # после подтверждения повторное письмо не отправляется
    client.post("/auth/resend-verification", json={"email": email})
    assert len(sent) == 2
    _cleanup(email)


def test_verify_email_rejects_bad_and_wrong_type_tokens(monkeypatch):
    client, _ = _client(monkeypatch)
    assert client.post("/auth/verify-email", json={"token": "garbage"}).status_code == 400
    access = main.create_access_token({"sub": "someone@example.com"})
    assert client.post("/auth/verify-email", json={"token": access}).status_code == 400


def test_resend_does_not_reveal_unknown_email(monkeypatch):
    client, sent = _client(monkeypatch)
    response = client.post("/auth/resend-verification", json={"email": "nobody@example.com"})
    assert response.status_code == 200
    assert sent == []


def test_resend_respects_cooldown(monkeypatch):
    email = "cooldown@example.com"
    _cleanup(email)
    client, sent = _client(monkeypatch)
    monkeypatch.setattr(main, "EMAIL_RESEND_COOLDOWN_SECONDS", 60)

    assert client.post("/auth/register", json={"email": email, "password": "secret123"}).status_code == 201
    assert len(sent) == 1

    # сразу после регистрации повторное письмо не уходит, но ответ тот же
    response = client.post("/auth/resend-verification", json={"email": email})
    assert response.status_code == 200
    assert response.json()["retry_after_seconds"] == 60
    assert len(sent) == 1

    # когда интервал прошёл — письмо уходит
    monkeypatch.setattr(main, "EMAIL_RESEND_COOLDOWN_SECONDS", 0)
    client.post("/auth/resend-verification", json={"email": email})
    assert len(sent) == 2
    _cleanup(email)


def test_concurrent_registration_returns_400_not_500(monkeypatch):
    """
    Имитируем гонку: второй запрос «не видит» первого пользователя при проверке
    (как будто оба запроса прошли проверку одновременно) и упирается в UNIQUE в БД.
    """
    email = "race@example.com"
    _cleanup(email)
    client, sent = _client(monkeypatch)
    assert client.post("/auth/register", json={"email": email, "password": "secret123"}).status_code == 201

    monkeypatch.setattr(main, "_find_user_by_email", lambda db, value: None)
    response = client.post("/auth/register", json={"email": email, "password": "secret123"})
    assert response.status_code == 400
    assert len(sent) == 1  # второе письмо не ушло
    _cleanup(email)


def test_email_is_case_insensitive(monkeypatch):
    email = "case@example.com"
    _cleanup(email)
    client, sent = _client(monkeypatch)
    assert client.post("/auth/register", json={"email": "Case@Example.com", "password": "secret123"}).status_code == 201
    assert client.post("/auth/register", json={"email": "case@example.com", "password": "secret123"}).status_code == 400
    client.post("/auth/verify-email", json={"token": sent[0][1]})
    assert client.post("/auth/login", data={"username": "CASE@example.com", "password": "secret123"}).status_code == 200
    _cleanup(email)


def test_resend_slot_is_claimed_only_once(monkeypatch):
    email = "slot@example.com"
    _cleanup(email)
    client, _ = _client(monkeypatch)
    monkeypatch.setattr(main, "EMAIL_RESEND_COOLDOWN_SECONDS", 60)
    client.post("/auth/register", json={"email": email, "password": "secret123"})
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        user.verification_email_sent_at = None
        db.commit()
        # первый запрос занимает слот, второй (пришедший сразу за ним) — уже нет
        assert main._claim_verification_email_slot(db, user) is True
        assert main._claim_verification_email_slot(db, user) is False
    finally:
        db.close()
    _cleanup(email)
