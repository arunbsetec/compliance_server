from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from server.core.security import hash_password, verify_password
from server.models.user import User
from server.schemas.auth import UserCreate, UserLogin


class EmailAlreadyRegistered(Exception):
    pass


class InvalidCredentials(Exception):
    pass


def register(db: Session, data: UserCreate) -> User:
    user = User(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise EmailAlreadyRegistered
    db.refresh(user)
    return user


def authenticate(db: Session, data: UserLogin) -> User:
    user = db.scalar(select(User).where(User.email == data.email))
    if user is None or not verify_password(data.password, user.password_hash):
        raise InvalidCredentials
    return user
