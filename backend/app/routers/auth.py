from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from .. import models
from ..database import get_db
from ..auth import verify_password, create_token, get_current_user

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == body.username).first()
    if not user or not user.active or not verify_password(body.password, user.password_hash):
        # deliberately identical error for "no such user" and "wrong password" —
        # distinguishing them lets an attacker enumerate valid usernames
        raise HTTPException(401, "invalid username or password")
    token = create_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in_hours": 12,
        "user": {
            "id": user.id, "username": user.username, "role": user.role,
            "display_name": user.display_name,
            "technician_id": user.technician_id, "client_name": user.client_name,
        },
    }


@router.get("/me")
def me(user: models.User = Depends(get_current_user)):
    return {
        "id": user.id, "username": user.username, "role": user.role,
        "display_name": user.display_name,
        "technician_id": user.technician_id, "client_name": user.client_name,
    }
