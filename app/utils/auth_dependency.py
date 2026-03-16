from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from jose import jwt

from app.utils.jwt_handler import SECRET_KEY, ALGORITHM

security = HTTPBearer()


def verify_token(credentials=Depends(security)):

    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload

    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    

from fastapi import Request, HTTPException

def require_login(request: Request):
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="Not authenticated")    