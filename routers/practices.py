from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from audit import record_audit
from auth import get_optional_current_user
from database import get_db
from models import Practice, User
from permissions import require_permission
from schemas import (
    PracticeAdminCreate,
    PracticeAdminUpdate,
    PracticeListResponse,
    PracticeResponse,
    PracticeSubmissionCreate,
)


router = APIRouter(tags=["practices"])

PRACTICE_LEVELS = {"Начальный", "Продвинутый", "Высший"}
PRACTICE_STATUSES = {"pending", "draft", "published", "archive"}


def _slugify(value: str) -> str:
    slug = re.sub(r"[^0-9a-zа-яё]+", "-", str(value or "").lower()).strip("-")
    return slug[:160] or f"praktika-{uuid4().hex[:8]}"


def _unique_slug(db: Session, value: str, current_id: int | None = None) -> str:
    candidate = _slugify(value)
    query = db.query(Practice).filter(Practice.slug == candidate)
    if current_id is not None:
        query = query.filter(Practice.id != current_id)
    if query.first() is None:
        return candidate
    return f"{candidate[:145].rstrip('-')}-{uuid4().hex[:8]}"


def _validate_status(value: str | None) -> str:
    normalized = str(value or "draft").strip().lower()
    if normalized not in PRACTICE_STATUSES:
        raise HTTPException(status_code=422, detail="Недопустимый статус практики")
    return normalized


def _validate_level(value: str | None) -> str:
    normalized = str(value or "Начальный").strip()
    if normalized not in PRACTICE_LEVELS:
        raise HTTPException(status_code=422, detail="Недопустимый уровень становления практики")
    return normalized


def _query_practices(
    db: Session,
    *,
    published_only: bool,
    q: str | None,
    topic: str | None,
    level: str | None,
    organization: str | None,
    status_filter: str | None = None,
):
    query = db.query(Practice)
    if published_only:
        query = query.filter(Practice.status == "published")
    elif status_filter and status_filter != "all":
        query = query.filter(Practice.status == status_filter)
    if q:
        needle = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Practice.title.ilike(needle),
                Practice.summary.ilike(needle),
                Practice.description.ilike(needle),
                Practice.organization.ilike(needle),
                Practice.author_name.ilike(needle),
            )
        )
    if topic:
        query = query.filter(Practice.topic == topic)
    if level:
        query = query.filter(Practice.level == level)
    if organization:
        query = query.filter(Practice.organization.ilike(f"%{organization.strip()}%"))
    return query


def _get_practice_or_404(db: Session, practice_id_or_slug: str, *, published_only: bool) -> Practice:
    query = db.query(Practice)
    if published_only:
        query = query.filter(Practice.status == "published")
    identifier = str(practice_id_or_slug)
    practice = query.filter(Practice.slug == identifier).first()
    if practice is None and identifier.isdigit():
        practice = query.filter(Practice.id == int(identifier)).first()
    if practice is None:
        raise HTTPException(status_code=404, detail="Практика не найдена")
    return practice


@router.get("/api/practices/", response_model=PracticeListResponse)
def list_public_practices(
    q: str | None = Query(None, max_length=120),
    topic: str | None = Query(None, max_length=200),
    level: str | None = Query(None, max_length=40),
    organization: str | None = Query(None, max_length=200),
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = _query_practices(
        db,
        published_only=True,
        q=q,
        topic=topic,
        level=level,
        organization=organization,
    )
    total = query.count()
    items = (
        query.order_by(Practice.published_at.desc().nullslast(), Practice.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"items": items, "total": total}


@router.post("/api/practices/submit/", response_model=PracticeResponse, status_code=status.HTTP_201_CREATED)
def submit_practice(
    data: PracticeSubmissionCreate,
    current_user: User | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    payload = data.model_dump()
    payload.pop("slug", None)
    practice = Practice(
        **payload,
        slug=_unique_slug(db, data.title),
        status="pending",
        created_by_id=getattr(current_user, "id", None),
    )
    db.add(practice)
    db.flush()
    record_audit(
        db,
        current_user,
        action="Подача практики",
        entity_type="practice",
        entity_id=practice.id,
        details={"title": practice.title, "status": practice.status, "topic": practice.topic},
    )
    db.commit()
    db.refresh(practice)
    return practice


@router.get("/api/practices/{practice_id_or_slug}", response_model=PracticeResponse)
def get_public_practice(practice_id_or_slug: str, db: Session = Depends(get_db)):
    return _get_practice_or_404(db, practice_id_or_slug, published_only=True)


@router.get("/api/admin/practices/", response_model=PracticeListResponse)
def list_admin_practices(
    q: str | None = Query(None, max_length=120),
    practice_status: str | None = Query("all", alias="status", max_length=20),
    topic: str | None = Query(None, max_length=200),
    level: str | None = Query(None, max_length=40),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: User = Depends(require_permission("articles", "view")),
    db: Session = Depends(get_db),
):
    if practice_status and practice_status != "all" and practice_status not in PRACTICE_STATUSES:
        raise HTTPException(status_code=422, detail="Недопустимый статус практики")
    query = _query_practices(
        db,
        published_only=False,
        q=q,
        topic=topic,
        level=level,
        organization=None,
        status_filter=practice_status,
    )
    total = query.count()
    items = query.order_by(Practice.updated_at.desc().nullslast(), Practice.id.desc()).offset(offset).limit(limit).all()
    return {"items": items, "total": total}


@router.post("/api/admin/practices/", response_model=PracticeResponse, status_code=status.HTTP_201_CREATED)
def create_practice(
    data: PracticeAdminCreate,
    current_user: User = Depends(require_permission("articles", "edit")),
    db: Session = Depends(get_db),
):
    payload = data.model_dump()
    payload["slug"] = _unique_slug(db, payload.get("slug") or payload["title"])
    payload["level"] = _validate_level(payload.get("level"))
    payload["status"] = _validate_status(payload.get("status"))
    payload["created_by_id"] = current_user.id
    if payload["status"] == "published":
        payload["published_at"] = datetime.now(timezone.utc)
    practice = Practice(**payload)
    db.add(practice)
    db.flush()
    record_audit(
        db,
        current_user,
        action="Создание практики",
        entity_type="practice",
        entity_id=practice.id,
        details={"title": practice.title, "status": practice.status, "topic": practice.topic},
    )
    db.commit()
    db.refresh(practice)
    return practice


@router.patch("/api/admin/practices/{practice_id}", response_model=PracticeResponse)
def update_practice(
    practice_id: int,
    data: PracticeAdminUpdate,
    current_user: User = Depends(require_permission("articles", "edit")),
    db: Session = Depends(get_db),
):
    practice = db.query(Practice).filter(Practice.id == practice_id).first()
    if practice is None:
        raise HTTPException(status_code=404, detail="Практика не найдена")
    changes = data.model_dump(exclude_unset=True)
    if "slug" in changes:
        changes["slug"] = _unique_slug(db, changes["slug"] or practice.title, current_id=practice.id)
    if "level" in changes:
        changes["level"] = _validate_level(changes["level"])
    if "status" in changes:
        changes["status"] = _validate_status(changes["status"])
        if changes["status"] == "published" and practice.published_at is None:
            changes["published_at"] = datetime.now(timezone.utc)
        elif changes["status"] != "published":
            changes["published_at"] = None
    for key, value in changes.items():
        setattr(practice, key, value)
    db.flush()
    record_audit(
        db,
        current_user,
        action="Изменение практики",
        entity_type="practice",
        entity_id=practice.id,
        details={"title": practice.title, "fields": list(changes), "status": practice.status},
    )
    db.commit()
    db.refresh(practice)
    return practice


@router.delete("/api/admin/practices/{practice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_practice(
    practice_id: int,
    current_user: User = Depends(require_permission("articles", "edit")),
    db: Session = Depends(get_db),
):
    practice = db.query(Practice).filter(Practice.id == practice_id).first()
    if practice is None:
        raise HTTPException(status_code=404, detail="Практика не найдена")
    title = practice.title
    db.delete(practice)
    record_audit(
        db,
        current_user,
        action="Удаление практики",
        entity_type="practice",
        entity_id=practice_id,
        details={"title": title},
    )
    db.commit()
