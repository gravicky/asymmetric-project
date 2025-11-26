from jwt import decode, ExpiredSignatureError, InvalidTokenError
from fastapi import HTTPException

from app.config import settings

security = HTTPBearer()

async def get_current_user(credentials = Depends(security)) -> dict:
    try:
        payload = decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=settings.ALGORITHM
        )
        return payload
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
