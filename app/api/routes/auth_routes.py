from fastapi import APIRouter, HTTPException, Depends
from pymongo import AsyncMongoClient

from app.api.schemas.auth_schemas import UserCreate, UserLogin, Token
from app.api.utils.auth_utils import hash_password, verify_password, create_token
from app.db.database import get_db

from app.config import settings

auth_router = APIRouter(prefix=settings.AUTH_PREFIX, tags=["auth"])

@auth_router.post("/signup")
async def signup(user: UserCreate, db: AsyncMongoClient = Depends(get_db)):
    existing = await db.users.find_one({"email": user.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_doc = {
        "email": user.email,
        "username": user.username,
        "password": hash_password(user.password)
    }
    result = await db.users.insert_one(user_doc)
    return {"user_id": str(result.inserted_id)}

@auth_router.post("/login", response_model=Token)
async def login(creds: UserLogin, db: AsyncMongoClient = Depends(get_db)):
    user = await db.users.find_one({"email": creds.email})
    if not user or not verify_password(creds.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_token(str(user["_id"]), user["email"])
    return {"access_token": token}

'''
for production code, we can add refresh tokens, rbac, etc
'''