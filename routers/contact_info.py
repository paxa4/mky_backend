from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from audit import record_audit
from database import get_db
from models import SiteContactInfo, User
from permissions import require_permission
from schemas import SiteContactInfoResponse, SiteContactInfoUpdate

router = APIRouter(tags=["contact-information"])


@router.get("/api/contact-info/", response_model=list[SiteContactInfoResponse])
def get_public_contact_info(db: Session = Depends(get_db)):
    return db.query(SiteContactInfo).order_by(SiteContactInfo.path.asc()).all()


@router.get(
    "/api/admin/contact-info/",
    response_model=list[SiteContactInfoResponse],
)
def get_admin_contact_info(
    _: User = Depends(require_permission("contact_info", "view")),
    db: Session = Depends(get_db),
):
    return db.query(SiteContactInfo).order_by(SiteContactInfo.path.asc()).all()


@router.put("/api/admin/contact-info/", response_model=SiteContactInfoResponse)
def save_contact_info(
    data: SiteContactInfoUpdate,
    current_user: User = Depends(require_permission("contact_info", "edit")),
    db: Session = Depends(get_db),
):
    record = db.query(SiteContactInfo).filter(SiteContactInfo.path == data.path).first()
    is_new = record is None
    if record is None:
        record = SiteContactInfo(path=data.path)
        db.add(record)

    record.title = data.title.strip()
    record.description = data.description.strip() if data.description else None
    record.contacts = [item.model_dump() for item in data.contacts]
    record.updated_by_id = current_user.id
    db.flush()
    record_audit(
        db,
        current_user,
        action="Изменение контактной информации",
        entity_type="site_contact_info",
        entity_id=record.id,
        details={
            "path": data.path,
            "title": record.title,
            "contacts_count": len(record.contacts),
            "created": is_new,
        },
    )
    db.commit()
    db.refresh(record)
    return record
