from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import get_current_user, hash_password
from audit import record_audit
from database import get_db
from models import User, UserRole
from permissions import normalize_role_permissions, require_admin_user
from schemas import RolePermissionsUpdate, RoleResponse, UserAdminCreate, UserAdminUpdate, UserResponse

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_admin_user)],
)


def _normalize_role_name(role_name: str | None) -> str | None:
    normalized = str(role_name or "").strip().lower()
    return normalized or None


def _role_or_400(db: Session, role_name: str | None) -> UserRole | None:
    normalized = _normalize_role_name(role_name)
    if normalized is None:
        return None
    role = db.query(UserRole).filter(UserRole.role_name == normalized).first()
    if not role:
        raise HTTPException(status_code=400, detail="Указанная роль не найдена")
    return role


def _ensure_unique_user_identity(
    db: Session,
    *,
    email: str | None = None,
    exclude_user_id: int | None = None,
) -> None:
    if email:
        query = db.query(User).filter(User.email == email)
        if exclude_user_id is not None:
            query = query.filter(User.id != exclude_user_id)
        if query.first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Пользователь с таким email уже существует",
            )


AUDIT_USER_FIELDS = (
    "email",
    "last_name",
    "first_name",
    "middle_name",
    "role",
    "is_active",
    "allowed_methodika_subjects",
)


def _user_role_name(db: Session, user: User) -> str:
    role = db.query(UserRole).filter(UserRole.id == user.role_id).first() if user.role_id else None
    return role.role_name if role else "user"


def _user_audit_snapshot(db: Session, user: User) -> dict:
    return {
        "email": user.email,
        "last_name": user.last_name,
        "first_name": user.first_name,
        "middle_name": user.middle_name,
        "role": _user_role_name(db, user),
        "is_active": bool(user.is_active),
        "allowed_methodika_subjects": list(user.allowed_methodika_subjects or []),
    }


def _audit_changes(before: dict | None, after: dict) -> list[dict]:
    return [
        {"field": field, "from": (before or {}).get(field), "to": after.get(field)}
        for field in AUDIT_USER_FIELDS
        if before is None or (before or {}).get(field) != after.get(field)
    ]

@router.get("/", response_model=List[UserResponse])
def get_all_users(db: Session = Depends(get_db)):
    """Получить список всех пользователей."""
    return db.query(User).order_by(User.id.asc()).all()


@router.get("/roles/", response_model=List[RoleResponse])
def get_all_roles(db: Session = Depends(get_db)):
    """Получить список доступных ролей пользователей."""
    roles = db.query(UserRole).order_by(UserRole.role_name.asc()).all()
    for role in roles:
        role.permissions = normalize_role_permissions(role.permissions, role.role_name)
    return roles


@router.put("/roles/{role_id}/permissions/", response_model=RoleResponse)
def update_role_permissions(
    role_id: int,
    permissions_data: RolePermissionsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Обновить права доступа выбранной роли к разделам системы."""
    role = db.query(UserRole).filter_by(id=role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Роль не найдена")

    before_permissions = normalize_role_permissions(role.permissions, role.role_name)
    after_permissions = normalize_role_permissions(permissions_data.permissions, role.role_name)
    permission_changes = [
        {"module": module_key, "from": before_permissions.get(module_key), "to": after_permissions.get(module_key)}
        for module_key in sorted(set(before_permissions) | set(after_permissions))
        if before_permissions.get(module_key) != after_permissions.get(module_key)
    ]
    role.permissions = after_permissions
    record_audit(
        db,
        current_user,
        action="Изменение прав роли",
        entity_type="role",
        entity_id=role.id,
        details={
            "role": role.role_name,
            "changes": permission_changes,
            "before": before_permissions,
            "after": after_permissions,
        },
    )
    db.commit()
    db.refresh(role)
    role.permissions = normalize_role_permissions(role.permissions, role.role_name)
    return role


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    """Получить одного пользователя по ID."""
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user_data: UserAdminCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Создать нового пользователя."""
    _ensure_unique_user_identity(db, email=user_data.email)
    role = _role_or_400(db, user_data.role)

    new_user = User(
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        last_name=user_data.last_name,
        first_name=user_data.first_name,
        middle_name=user_data.middle_name,
        is_active=user_data.is_active,
        role_id=role.id if role else None,
        allowed_methodika_subjects=user_data.allowed_methodika_subjects,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    after_snapshot = _user_audit_snapshot(db, new_user)
    record_audit(
        db,
        current_user,
        action="Создание пользователя",
        entity_type="user",
        entity_id=new_user.id,
        details={"changes": _audit_changes(None, after_snapshot), "after": after_snapshot},
    )
    db.commit()
    return new_user


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_data: UserAdminUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Обновить данные пользователя."""
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    before_snapshot = _user_audit_snapshot(db, user)
    payload = user_data.model_dump(exclude_unset=True)
    email = payload.get("email")
    _ensure_unique_user_identity(
        db,
        email=email,
        exclude_user_id=user.id,
    )

    if email is not None:
        user.email = email
    if "last_name" in payload:
        user.last_name = payload["last_name"]
    if "first_name" in payload:
        user.first_name = payload["first_name"]
    if "middle_name" in payload:
        user.middle_name = payload["middle_name"]
    if payload.get("password"):
        user.password_hash = hash_password(payload["password"])
    if "is_active" in payload:
        user.is_active = payload["is_active"]
    if "allowed_methodika_subjects" in payload:
        user.allowed_methodika_subjects = payload["allowed_methodika_subjects"] or []
    if "role" in payload:
        role = _role_or_400(db, payload["role"])
        user.role_id = role.id if role else None

    db.commit()
    db.refresh(user)
    after_snapshot = _user_audit_snapshot(db, user)
    record_audit(
        db,
        current_user,
        action="Изменение пользователя",
        entity_type="user",
        entity_id=user.id,
        details={"changes": _audit_changes(before_snapshot, after_snapshot), "before": before_snapshot, "after": after_snapshot},
    )
    db.commit()
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Удалить пользователя."""
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    before_snapshot = _user_audit_snapshot(db, user)
    db.delete(user)
    db.commit()
    record_audit(
        db,
        current_user,
        action="Удаление пользователя",
        entity_type="user",
        entity_id=user_id,
        details={"changes": _audit_changes(before_snapshot, {field: None for field in AUDIT_USER_FIELDS}), "before": before_snapshot},
    )
    db.commit()
    return None
