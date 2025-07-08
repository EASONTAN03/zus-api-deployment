from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import time
from collections import defaultdict
from .utils import load_config
import os
import json
from passlib.context import CryptContext
from datetime import datetime, timedelta

config = load_config()

# --- Auth constants ---
SECRET_KEY = config.get("auth", {}).get("secret_key", "a-string-secret-at-least-256-bits-long")
ALGORITHM = config.get("auth", {}).get("algorithm", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = config.get("auth", {}).get("access_token_expire_minutes", 60)
USER_FILE = config.get("auth", {}).get("user_file", "data/users.json")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def load_users():
    if not os.path.exists(USER_FILE):
        return {}
    with open(USER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_users(users):
    os.makedirs(os.path.dirname(USER_FILE), exist_ok=True)
    with open(USER_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)

# Utility to create JWT
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

async def get_user_identifier(token: Optional[str] = Depends(oauth2_scheme)):
    if token is None:
        return "global_unauthenticated_user"
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return "global_unauthenticated_user"
        return username
    except JWTError:
        return "global_unauthenticated_user"

# --- Rate limiting constants ---
rate_limit_config = config.get("rate_limit", {})
AUTH_RATE_LIMIT = rate_limit_config.get("auth_rate_limit", 5)
AUTH_TIME_WINDOW_SECONDS = rate_limit_config.get("auth_time_window_seconds", 60)
GLOBAL_RATE_LIMIT = rate_limit_config.get("global_rate_limit", 3)
GLOBAL_TIME_WINDOW_SECONDS = rate_limit_config.get("global_time_window_seconds", 60)

# --- In-memory storage for user requests ---
user_requests = defaultdict(list)

# --- Throttling dependency ---
def apply_rate_limit(user_id: str = Depends(get_user_identifier)):
    current_time = time.time()
    if user_id == "global_unauthenticated_user":
        rate_limit = GLOBAL_RATE_LIMIT
        time_window = GLOBAL_TIME_WINDOW_SECONDS
    else:
        rate_limit = AUTH_RATE_LIMIT
        time_window = AUTH_TIME_WINDOW_SECONDS
    # Filter out requests older than the time window
    user_requests[user_id] = [
        t for t in user_requests[user_id] if t > current_time - time_window
    ]
    current_usage = len(user_requests[user_id])
    print(f"[RateLimit] User {user_id}: {current_usage + 1}/{rate_limit} requests used in the last {time_window} seconds.")
    if current_usage >= rate_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )
    user_requests[user_id].append(current_time)
    return True 