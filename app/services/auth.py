from __future__ import annotations

import os
from typing import Optional
from jose import jwt
from fastapi import Header, HTTPException, status

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")


def verify_jwt_and_get_user_id(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing auth token")
    token = authorization.split(" ", 1)[1]
    if not SUPABASE_JWT_SECRET:
        # In dev, accept any token as user 'default'
        return "default"
    try:
        payload = jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"])
        sub = payload.get("sub") or payload.get("user_id") or "default"
        return str(sub)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")