from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.auth import create_access_token, get_current_user, hash_password, verify_password
from backend.database import get_db
from backend.models import User, UserSettings
from backend.schemas import LoginReq, RegisterReq, TokenResp

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResp)
def register(req: RegisterReq, db: Session = Depends(get_db)):
    if len(req.username) < 2:
        raise HTTPException(400, "用户名至少2个字符")
    if len(req.password) < 6:
        raise HTTPException(400, "密码至少6位")
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(400, "用户名已存在")
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(400, "邮箱已被注册")

    user = User(username=req.username, email=req.email, password_hash=hash_password(req.password))
    db.add(user)
    db.flush()
    db.add(UserSettings(user_id=user.id))
    db.commit()
    db.refresh(user)

    return TokenResp(
        access_token=create_access_token(user.id),
        user_id=user.id,
        username=user.username,
        email=user.email,
    )


@router.post("/login", response_model=TokenResp)
def login(req: LoginReq, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        (User.username == req.username) | (User.email == req.username)
    ).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    if not user.is_active:
        raise HTTPException(403, "账号已被禁用")

    return TokenResp(
        access_token=create_access_token(user.id),
        user_id=user.id,
        username=user.username,
        email=user.email,
    )


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else "",
    }
