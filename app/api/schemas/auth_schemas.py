from pydantic import BaseModel, EmailStr

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserCreate(UserLogin):
    username: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"