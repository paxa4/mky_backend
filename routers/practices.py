from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from audit import record_audit
from auth import get_optional_current_user
from database import get_db
from models import Practice, PracticeConclusion, User
from permissions import require_permission
from schemas import (
    PracticeAdminCreate,
    PracticeAdminUpdate,
    PracticeConclusionCreate,
    PracticeConclusionListResponse,
    PracticeConclusionResponse,
    PracticeListResponse,
    PracticeMapResponse,
    PracticeResponse,
    PracticeStatisticsResponse,
    PracticeSubmissionCreate,
)


router = APIRouter(tags=["practices"])

PRACTICE_LEVELS = {"Начальный", "Продвинутый", "Высший"}
PRACTICE_UNASSIGNED_LEVEL = "Не присвоен"
PRACTICE_STATUSES = {"pending", "draft", "published", "archive"}


@router.get("/api/practices/statistics/", response_model=PracticeStatisticsResponse)
def get_public_practice_statistics(db: Session = Depends(get_db)):
    rows = (
        db.query(Practice.topic, Practice.level, func.count(Practice.id))
        .filter(Practice.status == "published")
        .group_by(Practice.topic, Practice.level)
        .all()
    )
    by_level = {level: 0 for level in PRACTICE_LEVELS}
    by_topic: dict[str, dict] = {}
    total = 0
    for topic, level, count in rows:
        count = int(count)
        total += count
        by_level[level] = by_level.get(level, 0) + count
        topic_data = by_topic.setdefault(topic, {"topic": topic, "total": 0, "levels": {key: 0 for key in PRACTICE_LEVELS}})
        topic_data["total"] += count
        topic_data["levels"][level] = topic_data["levels"].get(level, 0) + count
    return {
        "total": total,
        "by_level": by_level,
        "by_topic": sorted(by_topic.values(), key=lambda item: item["topic"].casefold()),
    }


@router.get("/api/practices/map/", response_model=PracticeMapResponse)
def get_public_practice_map(db: Session = Depends(get_db)):
    query = db.query(Practice).filter(Practice.status == "published")
    located = (
        query.filter(Practice.latitude.isnot(None), Practice.longitude.isnot(None))
        .order_by(Practice.title.asc())
        .all()
    )
    unlocated_total = query.filter(or_(Practice.latitude.is_(None), Practice.longitude.is_(None))).count()
    return {"items": located, "total": len(located), "unlocated_total": unlocated_total}


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
    if normalized not in PRACTICE_LEVELS | {PRACTICE_UNASSIGNED_LEVEL}:
        raise HTTPException(status_code=422, detail="Недопустимый уровень становления практики")
    return normalized


def _public_practice_payload(practice: Practice) -> dict:
    payload = PracticeResponse.model_validate(practice).model_dump()
    payload["author_email"] = None
    application_data = dict(payload.get("application_data") or {})
    for key in ("curator_work_phone", "curator_email", "curator_mobile"):
        application_data.pop(key, None)
    payload["application_data"] = application_data
    return payload


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
    return {"items": [_public_practice_payload(item) for item in items], "total": total}


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
    return _public_practice_payload(practice)


@router.get(
    "/api/practices/{practice_id_or_slug}/conclusions/",
    response_model=PracticeConclusionListResponse,
)
def get_practice_conclusions(
    practice_id_or_slug: str,
    current_user: User | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    practice = _get_practice_or_404(db, practice_id_or_slug, published_only=True)
    conclusions = (
        db.query(PracticeConclusion)
        .filter(PracticeConclusion.practice_id == practice.id)
        .order_by(PracticeConclusion.created_at.asc(), PracticeConclusion.id.asc())
        .all()
    )
    items = [
        {
            "id": item.id,
            "practice_id": item.practice_id,
            "expert_name": item.expert_name,
            "content": item.content,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "is_mine": bool(current_user and item.expert_user_id == current_user.id),
        }
        for item in conclusions
    ]
    return {"items": items, "total": len(items)}


@router.post(
    "/api/practices/{practice_id_or_slug}/conclusions/",
    response_model=PracticeConclusionResponse,
)
def save_practice_conclusion(
    practice_id_or_slug: str,
    data: PracticeConclusionCreate,
    current_user: User = Depends(require_permission("practice_expert", "edit")),
    db: Session = Depends(get_db),
):
    practice = _get_practice_or_404(db, practice_id_or_slug, published_only=True)
    conclusion = (
        db.query(PracticeConclusion)
        .filter(
            PracticeConclusion.practice_id == practice.id,
            PracticeConclusion.expert_user_id == current_user.id,
        )
        .first()
    )
    is_new = conclusion is None
    expert_name = " ".join(
        part for part in (current_user.last_name, current_user.first_name, current_user.middle_name) if part
    ) or current_user.email
    if is_new:
        conclusion = PracticeConclusion(
            practice_id=practice.id,
            expert_user_id=current_user.id,
            expert_name=expert_name,
            content=data.content,
        )
        db.add(conclusion)
    else:
        conclusion.expert_name = expert_name
        conclusion.content = data.content
        conclusion.updated_at = datetime.now(timezone.utc)
    db.flush()
    record_audit(
        db,
        current_user,
        action="Экспертное заключение по практике",
        entity_type="practice",
        entity_id=practice.id,
        details={"title": practice.title, "operation": "создание" if is_new else "обновление"},
    )
    db.commit()
    db.refresh(conclusion)
    return {
        "id": conclusion.id,
        "practice_id": conclusion.practice_id,
        "expert_name": conclusion.expert_name,
        "content": conclusion.content,
        "created_at": conclusion.created_at,
        "updated_at": conclusion.updated_at,
        "is_mine": True,
    }


@router.get("/api/practices/{practice_id_or_slug}", response_model=PracticeResponse)
def get_public_practice(practice_id_or_slug: str, db: Session = Depends(get_db)):
    practice = _get_practice_or_404(db, practice_id_or_slug, published_only=True)
    return _public_practice_payload(practice)


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
    if payload["status"] == "published" and payload["level"] == PRACTICE_UNASSIGNED_LEVEL:
        raise HTTPException(status_code=422, detail="Перед публикацией назначьте уровень становления по итогам экспертизы")
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
    if changes.get("status", practice.status) == "published" and changes.get("level", practice.level) == PRACTICE_UNASSIGNED_LEVEL:
        raise HTTPException(status_code=422, detail="Перед публикацией назначьте уровень становления по итогам экспертизы")
    latitude = changes.get("latitude", practice.latitude)
    longitude = changes.get("longitude", practice.longitude)
    if (latitude is None) != (longitude is None):
        raise HTTPException(status_code=422, detail="Широта и долгота должны быть указаны вместе")
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
