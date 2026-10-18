from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models import AuditLog
from permissions import require_permission
from schemas import AuditLogResponse

router = APIRouter(prefix="/audit-log", tags=["audit"])


@router.get("/", response_model=list[AuditLogResponse])
def list_audit_log(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    entity_type: list[str] | None = Query(None),
    _: object = Depends(require_permission("audit_log", "view")),
    db: Session = Depends(get_db),
):
    query = db.query(AuditLog)
    if entity_type:
        query = query.filter(AuditLog.entity_type.in_(entity_type))
    return (
        query
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
