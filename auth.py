"""
Urban Lex Tracker — Authentication Module
JWT tokens + bcrypt password hashing.
"""
import os
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Request
from dotenv import load_dotenv

import database

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "ult-fallback-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24 * 7  # 7 days

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ─── Password Utilities ───

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ─── JWT Utilities ───

def create_access_token(user_id: int, email: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


# ─── Auth Actions ───

def login_user(email: str, password: str) -> dict:
    user = database.get_user_by_email(email.strip().lower())
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos"
        )
    if not verify_password(password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos"
        )
    token = create_access_token(user["id"], user["email"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "nombre": user["nombre"],
            "profesion": user["profesion"]
        }
    }


def register_user(email: str, password: str, nombre: str = "", profesion: str = "") -> dict:
    email = email.strip().lower()
    existing = database.get_user_by_email(email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con este correo"
        )
    hashed = hash_password(password)
    user = database.create_user(email, hashed, nombre, profesion)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear la cuenta"
        )
    token = create_access_token(user["id"], user["email"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "nombre": user["nombre"],
            "profesion": user["profesion"]
        }
    }


def get_current_user_from_request(request: Request) -> Optional[dict]:
    """Extract and validate JWT from Authorization header or cookie."""
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    if not token:
        token = request.cookies.get("ult_token")
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    user_id = int(payload.get("sub", 0))
    return database.get_user_by_id(user_id)


def require_auth(request: Request) -> dict:
    """Dependency that raises 401 if not authenticated."""
    user = get_current_user_from_request(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado"
        )
    return user


def seed_demo_user():
    """Create the demo user if it doesn't exist."""
    email = "matias@agorarevision.cl"
    existing = database.get_user_by_email(email)
    if not existing:
        hashed = hash_password("Agora05522")
        database.create_user(
            email=email,
            hashed_password=hashed,
            nombre="Matías Agora",
            profesion="Arquitecto/a"
        )
        print(f"[AUTH] Demo user created: {email}")
    else:
        print(f"[AUTH] Demo user already exists: {email}")
