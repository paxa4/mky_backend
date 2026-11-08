"""
email_service.py — отправка писем через SMTP.

Все настройки берутся из переменных окружения (.env):
    SMTP_HOST, SMTP_PORT          — адрес и порт SMTP-сервера
    SMTP_USER, SMTP_PASSWORD      — логин и пароль (для Mailpit не нужны)
    SMTP_USE_SSL                  — true для порта 465 (SSL с самого начала)
    SMTP_USE_TLS                  — true для порта 587 (STARTTLS)
    MAIL_FROM                     — адрес отправителя
    FRONTEND_URL                  — адрес сайта, из него собирается ссылка в письме
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import quote

logger = logging.getLogger("email_service")


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "1025"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_USE_SSL = _env_bool("SMTP_USE_SSL")
SMTP_USE_TLS = _env_bool("SMTP_USE_TLS")
SMTP_TIMEOUT_SECONDS = float(os.getenv("SMTP_TIMEOUT_SECONDS", "15"))
MAIL_FROM = os.getenv("MAIL_FROM", "noreply@mky.local")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")


def send_email(to: str, subject: str, text: str, html: str | None = None) -> None:
    """Отправляет одно письмо. При ошибке выбрасывает исключение."""
    message = EmailMessage()
    message["From"] = MAIL_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)            # текстовая версия — для почтовиков без HTML
    if html:
        message.add_alternative(html, subtype="html")

    if SMTP_USE_SSL:
        server = smtplib.SMTP_SSL(
            SMTP_HOST, SMTP_PORT,
            timeout=SMTP_TIMEOUT_SECONDS,
            context=ssl.create_default_context(),
        )
    else:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS)

    with server:
        if SMTP_USE_TLS and not SMTP_USE_SSL:
            server.starttls(context=ssl.create_default_context())
        if SMTP_USER:
            server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(message)


def build_verification_link(token: str) -> str:
    return f"{FRONTEND_URL}/verify-email?token={quote(token)}"


def send_verification_email(to: str, token: str) -> None:
    """
    Отправляет письмо со ссылкой подтверждения.
    Вызывается в фоне (BackgroundTasks), поэтому ошибки не выбрасывает,
    а пишет в лог: регистрация уже прошла, пользователь сможет
    запросить письмо повторно.
    """
    link = build_verification_link(token)
    subject = "Подтверждение регистрации на сайте МКУ ИМЦРО"
    text = (
        "Здравствуйте!\n\n"
        "Вы зарегистрировались на сайте МКУ ИМЦРО. "
        "Чтобы подтвердить адрес электронной почты, перейдите по ссылке:\n\n"
        f"{link}\n\n"
        "Ссылка действует 24 часа. "
        "Если вы не регистрировались, просто проигнорируйте это письмо."
    )
    html = f"""\
<p>Здравствуйте!</p>
<p>Вы зарегистрировались на сайте МКУ ИМЦРО.
Чтобы подтвердить адрес электронной почты, нажмите на кнопку:</p>
<p><a href="{link}" style="display:inline-block;padding:10px 20px;background:#1d4ed8;color:#ffffff;text-decoration:none;border-radius:6px">Подтвердить почту</a></p>
<p>Или скопируйте ссылку в браузер:<br><a href="{link}">{link}</a></p>
<p style="color:#64748b">Ссылка действует 24 часа. Если вы не регистрировались, просто проигнорируйте это письмо.</p>
"""
    try:
        send_email(to, subject, text, html)
        logger.info("[email] verification email sent to %s", to)
    except Exception as exc:  # noqa: BLE001 — любая ошибка SMTP не должна ронять приложение
        logger.error("[email] failed to send verification email to %s: %s", to, exc)
