from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import User, UserSettings
from backend.schemas import UserSettingsReq, UserSettingsResp

router = APIRouter(prefix="/api/user", tags=["user"])


def _get_or_create_settings(user: User, db: Session) -> UserSettings:
    if not user.settings:
        s = UserSettings(user_id=user.id)
        db.add(s)
        db.commit()
        db.refresh(user)
    return user.settings


@router.get("/settings", response_model=UserSettingsResp)
def get_settings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _get_or_create_settings(current_user, db)
    return UserSettingsResp(
        ai_api_key=s.ai_api_key or "",
        ai_base_url=s.ai_base_url or "https://yunwu.ai/v1",
        ai_model=s.ai_model or "gpt-4o",
        email_enabled=s.email_enabled or False,
        email_smtp_host=s.email_smtp_host or "smtp.qq.com",
        email_smtp_port=s.email_smtp_port or 465,
        email_sender=s.email_sender or "",
        email_sender_pass=s.email_sender_pass or "",
        email_receiver=s.email_receiver or "",
        notify_min_confidence=s.notify_min_confidence or 0.60,
        initial_capital=s.initial_capital or 100000.0,
    )


@router.put("/settings")
def update_settings(
    req: UserSettingsReq,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    s = _get_or_create_settings(current_user, db)
    for field, value in req.model_dump(exclude_none=True).items():
        setattr(s, field, value)
    db.commit()
    return {"status": "ok"}


@router.get("/profile")
def get_profile(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else "",
    }
