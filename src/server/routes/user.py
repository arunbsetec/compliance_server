from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.core.deps import get_current_user
from server.core.security import create_access_token
from server.db.session import get_db
from server.models.user import User
from server.schemas.auth import TokenResponse, UserCreate, UserLogin, UserResponse
from server.services import auth_service

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=201)
def register(data: UserCreate, db: Annotated[Session, Depends(get_db)]) -> User:
    try:
        return auth_service.register(db, data)
    except auth_service.EmailAlreadyRegistered:
        raise HTTPException(status_code=409, detail="Email already registered")


@router.post("/login", response_model=TokenResponse)
def login(data: UserLogin, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    try:
        user = auth_service.authenticate(db, data)
    except auth_service.InvalidCredentials:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserResponse)
def me(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    return current_user
