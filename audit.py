from __future__ import annotations

from typing import Any

from models import AuditLog


def record_audit(
    db,
    user,
    *,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Add one audit event to the current transaction."""
    fio = " ".join(
        part for part in (
            getattr(user, "last_name", None),
            getattr(user, "first_name", None),
            getattr(user, "middle_name", None),
        )
        if part
    ).strip()
    entry = AuditLog(
        user_id=getattr(user, "id", None),
        user_name=fio or getattr(user, "email", None),
        user_email=getattr(user, "email", None),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details or {},
    )
    db.add(entry)
    return entry
