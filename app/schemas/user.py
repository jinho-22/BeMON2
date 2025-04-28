from pydantic import BaseModel, EmailStr
from typing import Optional

class UserCreate(BaseModel):
    username: str
    password: str
    name: str
    email: Optional[EmailStr] = None

class UserLogin(BaseModel):
    username: str
    password: str

class UserOut(BaseModel):
    user_id: int
    username: str
    name: str
    email: Optional[EmailStr]

    class Config:
        orm_mode = True