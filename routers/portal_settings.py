from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from audit import record_audit
from database import get_db
from models import PortalSettings, User
from permissions import require_permission
from schemas import PortalSettingsResponse, PortalSettingsUpdate

router = APIRouter(prefix="/portal", tags=["portal-settings"])


def _get_or_create_settings(db: Session) -> PortalSettings:
    settings = db.query(PortalSettings).filter(PortalSettings.id == 1).first()
    if settings is None:
        settings = PortalSettings(id=1, portal_name="МКУ ИМЦРО")
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.get("/settings", response_model=PortalSettingsResponse)
def get_portal_settings(
    _: object = Depends(require_permission("portal_settings", "view")),
    db: Session = Depends(get_db),
):
    return _get_or_create_settings(db)


@router.put("/settings", response_model=PortalSettingsResponse)
def update_portal_settings(
    data: PortalSettingsUpdate,
    current_user: User = Depends(require_permission("portal_settings", "edit")),
    db: Session = Depends(get_db),
):
    settings = _get_or_create_settings(db)
    for key, value in data.model_dump().items():
        setattr(settings, key, value.strip() if isinstance(value, str) else value)
    settings.updated_by_id = current_user.id
    record_audit(
        db,
        current_user,
        action="Изменение настроек портала",
        entity_type="portal_settings",
        entity_id=settings.id,
        details={"fields": list(data.model_dump().keys())},
    )
    db.commit()
    db.refresh(settings)
    return settings
